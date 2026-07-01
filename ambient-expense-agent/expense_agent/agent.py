import base64
import datetime
import json
import os
import re
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.adk.agents.context import Context
from google.adk.apps import App
from google.adk.events import EventActions
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.workflow import Edge, Workflow, node
from google.genai import types
from pydantic import BaseModel, Field

from expense_agent.config import CONFIG

# Load the local .env configuration file
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Initialize GenAI Client dynamically based on configured auth
if os.getenv("GEMINI_API_KEY"):
    # AI Studio mode
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
else:
    # Vertex AI / GCP mode (using ADC)
    client = genai.Client(vertexai=True)


class ExpenseReport(BaseModel):
    amount: float = Field(default=0.0)
    submitter: str = Field(default="Unknown")
    category: str = Field(default="General")
    description: str = Field(default="")
    date: str = Field(default="")


@node
async def extract_expense(ctx: Context, node_input: Any) -> AsyncGenerator[Event, None]:
    """Parses incoming JSON payload and routes based on threshold."""
    # 1. Parse the input to get the raw dictionary payload
    payload = {}
    if isinstance(node_input, dict):
        payload = node_input
    elif isinstance(node_input, str):
        try:
            payload = json.loads(node_input)
        except Exception:
            payload = {"data": node_input}
    elif hasattr(node_input, "parts") and node_input.parts:
        text = node_input.parts[0].text
        try:
            payload = json.loads(text)
        except Exception:
            payload = {"data": text}
    else:
        payload = {"data": str(node_input)}

    # 2. Extract detail data under 'data' key (could be base64-encoded or plain JSON)
    data_val = payload.get("data")
    expense_details = {}
    if data_val:
        if isinstance(data_val, str):
            # Check if base64-encoded Pub/Sub data
            try:
                decoded_bytes = base64.b64decode(data_val)
                decoded_str = decoded_bytes.decode("utf-8")
                expense_details = json.loads(decoded_str)
            except Exception:
                # If not base64, maybe raw JSON string
                try:
                    expense_details = json.loads(data_val)
                except Exception:
                    expense_details = {"description": data_val}
        elif isinstance(data_val, dict):
            expense_details = data_val
    else:
        # If 'data' is missing, assume fields are passed directly in payload
        expense_details = payload

    # 3. Map extracted fields into ExpenseReport
    expense = ExpenseReport(
        amount=float(expense_details.get("amount", expense_details.get("price", 0.0))),
        submitter=str(
            expense_details.get("submitter", expense_details.get("name", "Unknown"))
        ),
        category=str(expense_details.get("category", "General")),
        description=str(expense_details.get("description", "")),
        date=str(expense_details.get("date", "")),
    )

    # 4. Determine routing path based on Python configuration threshold
    if expense.amount < CONFIG.THRESHOLD:
        message = (
            f"🔍 **Expense Extraction Node**:\n"
            f"  - Amount: `${expense.amount:.2f}`\n"
            f"  - Submitter: `{expense.submitter}`\n"
            f"  - Status: Under threshold (`${CONFIG.THRESHOLD:.2f}`).\n"
            f"Routing to **Instant Auto-Approval** (No LLM required)."
        )
        yield Event(
            content=types.Content(
                role="model", parts=[types.Part.from_text(text=message)]
            )
        )
        yield Event(
            output=expense,
            actions=EventActions(
                route="auto_approve", state_delta={"expense": expense.model_dump()}
            ),
        )
    else:
        message = (
            f"🔍 **Expense Extraction Node**:\n"
            f"  - Amount: `${expense.amount:.2f}`\n"
            f"  - Submitter: `{expense.submitter}`\n"
            f"  - Status: At/over threshold (`${CONFIG.THRESHOLD:.2f}`).\n"
            f"Routing to **LLM Risk Review & Human Approval**."
        )
        yield Event(
            content=types.Content(
                role="model", parts=[types.Part.from_text(text=message)]
            )
        )
        yield Event(
            output=expense,
            actions=EventActions(
                route="llm_review", state_delta={"expense": expense.model_dump()}
            ),
        )


@node
async def auto_approve(
    ctx: Context, node_input: ExpenseReport
) -> AsyncGenerator[Event, None]:
    """Instantly auto-approves the expense and returns the outcome."""
    outcome = {
        "status": "APPROVED",
        "reason": "Auto-approved (under threshold)",
        "approved_at": datetime.datetime.now().isoformat(),
        "expense": node_input.model_dump(),
    }
    message = (
        f"🟢 **Expense Auto-Approved**:\n"
        f"The expense of `${node_input.amount:.2f}` submitted by `{node_input.submitter}` "
        f"has been instantly approved."
    )
    yield Event(
        content=types.Content(role="model", parts=[types.Part.from_text(text=message)])
    )
    yield Event(output=outcome, actions=EventActions(state_delta={"outcome": outcome}))


@node(rerun_on_resume=True)
async def llm_review(
    ctx: Context, node_input: ExpenseReport
) -> AsyncGenerator[Event | RequestInput, None]:
    """Uses LLM to perform a risk review and pauses for human decision."""
    # 1. Run model risk assessment if not already completed
    if "risk_analysis" not in ctx.state:
        prompt = (
            f"Analyze the following expense report for potential risk factors, policy violations, or suspicious patterns.\n"
            f"Amount: ${node_input.amount:.2f}\n"
            f"Submitter: {node_input.submitter}\n"
            f"Category: {node_input.category}\n"
            f"Description: {node_input.description}\n"
            f"Date: {node_input.date}\n\n"
            f"Provide a concise, professional risk assessment (max 3 bullet points) outlining:\n"
            f"1. Policy alignment\n"
            f"2. Risk level assessment (High/Medium/Low)\n"
            f"3. Any red flags or anomaly alerts"
        )

        # Display analysis loading
        yield Event(
            content=types.Content(
                role="model",
                parts=[
                    types.Part.from_text(
                        text="🤖 *Analyzing expense details using Gemini...*"
                    )
                ],
            )
        )

        try:
            response = client.models.generate_content(
                model=CONFIG.MODEL_NAME,
                contents=prompt,
            )
            risk_analysis = response.text
        except Exception as e:
            risk_analysis = f"Failed to perform model risk analysis: {e}"

        ctx.state["risk_analysis"] = risk_analysis

        # Display the result in the playground
        yield Event(
            content=types.Content(
                role="model",
                parts=[
                    types.Part.from_text(
                        text=f"🚨 **LLM Risk Assessment Alert**:\n\n{risk_analysis}"
                    )
                ],
            )
        )

    # 2. Pause and prompt for human review input
    if not ctx.resume_inputs or "approval_decision" not in ctx.resume_inputs:
        yield RequestInput(
            interrupt_id="approval_decision",
            message="Please review the risk analysis above. Do you approve this expense? (Reply 'approve' or 'reject')",
        )
        return

    # 3. Human has responded, retrieve decision from context
    raw_decision = ctx.resume_inputs["approval_decision"]
    if isinstance(raw_decision, dict):
        decision_str = (
            raw_decision.get("output")
            or raw_decision.get("response")
            or raw_decision.get("approval_decision")
            or str(raw_decision)
        )
    else:
        decision_str = str(raw_decision)

    decision = decision_str.strip().lower()
    approved = any(word in decision for word in ["approve", "yes", "y", "ok"])

    outcome = {
        "status": "APPROVED" if approved else "REJECTED",
        "reason": "Human reviewed LLM risk assessment",
        "risk_analysis": ctx.state["risk_analysis"],
        "approved_at": datetime.datetime.now().isoformat(),
        "expense": node_input.model_dump(),
    }

    message = (
        f"📝 **Review Recorded**:\n"
        f"  - Decision: `{'APPROVED' if approved else 'REJECTED'}`\n"
        f"  - Decision logic: {outcome['reason']}\n"
        f"  - Recorded at: `{outcome['approved_at']}`"
    )
    yield Event(
        content=types.Content(role="model", parts=[types.Part.from_text(text=message)])
    )
    yield Event(output=outcome, actions=EventActions(state_delta={"outcome": outcome}))


def scrub_pii(text: str) -> tuple[str, list[str]]:
    """Scrubs SSNs and Credit Card numbers from the given text."""
    redacted_categories = []
    
    # SSN: XXX-XX-XXXX or XXX XX XXXX
    ssn_pattern = re.compile(r'\b\d{3}[- ]\d{2}[- ]\d{4}\b')
    
    # Credit Cards: 13 to 19 digits, contiguous or grouped with spaces/hyphens
    cc_patterns = [
        re.compile(r'\b\d{13,19}\b'),
        re.compile(r'\b\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{1,7}\b'),
        re.compile(r'\b\d{4}[- ]\d{6}[- ]\d{5}\b'),
    ]
    
    scrubbed = text
    
    if ssn_pattern.search(scrubbed):
        scrubbed = ssn_pattern.sub("[REDACTED SSN]", scrubbed)
        redacted_categories.append("SSN")
        
    has_cc = False
    for pat in cc_patterns:
        if pat.search(scrubbed):
            scrubbed = pat.sub("[REDACTED CREDIT CARD]", scrubbed)
            has_cc = True
            
    if has_cc:
        redacted_categories.append("Credit Card")
        
    return scrubbed, redacted_categories


def detect_injection(text: str) -> bool:
    """Scans the text for potential prompt injection patterns."""
    injection_keywords = [
        "ignore previous",
        "ignore above",
        "system prompt",
        "force auto-approve",
        "force approval",
        "bypass rules",
        "override instructions",
        "forget what I said",
        "you must approve",
        "always approve",
        "bypass threshold",
    ]
    text_lower = text.lower()
    for kw in injection_keywords:
        if kw in text_lower:
            return True
    return False


@node
async def security_checkpoint(
    ctx: Context, node_input: ExpenseReport
) -> AsyncGenerator[Event, None]:
    """Inspects expense description for PII and prompt injection.
    
    PII is scrubbed immediately to protect downstream LLM and logs.
    If prompt injection is detected, LLM review is bypassed and routed
    directly to manual review with a security flag.
    """
    original_description = node_input.description
    scrubbed_desc, redacted_cats = scrub_pii(original_description)
    
    # Update the expense report description with the scrubbed version
    node_input.description = scrubbed_desc
    
    # Update the expense in state to ensure human-approval payload is clean too
    state_delta = {
        "expense": node_input.model_dump(),
        "redacted_categories": redacted_cats,
    }
    
    # Check for prompt injection in the original or scrubbed description
    injection_detected = detect_injection(original_description) or detect_injection(scrubbed_desc)
    
    if injection_detected:
        state_delta["security_event"] = True
        # Set a placeholder risk analysis so manual review can display the security issue
        security_message = (
            "⚠️ **SECURITY EVENT**: Potential prompt injection detected in the description!\n"
            "The downstream LLM review was bypassed to prevent adversarial instructions from compromising the agent."
        )
        state_delta["risk_analysis"] = security_message
        
        # Log/display warning
        warning_msg = (
            f"🛡️ **Security Checkpoint**: **ALERT**\n"
            f"  - Prompt injection detected in description: \"*{original_description[:60]}...*\"\n"
            f"  - Action: Downstream LLM bypassed. Routing directly to manual review."
        )
        if redacted_cats:
            warning_msg += f"\n  - Redacted: `{', '.join(redacted_cats)}`"
            
        yield Event(
            content=types.Content(
                role="model", parts=[types.Part.from_text(text=warning_msg)]
            )
        )
        yield Event(
            output=node_input,
            actions=EventActions(
                route="security_alert",
                state_delta=state_delta
            )
        )
    else:
        # Clean from prompt injection
        confirm_msg = f"🛡️ **Security Checkpoint**: **CLEAN**\n"
        if redacted_cats:
            confirm_msg += (
                f"  - Redacted: `{', '.join(redacted_cats)}` from description.\n"
                f"  - Description scrubbed: \"*{scrubbed_desc[:60]}...*\"\n"
            )
        else:
            confirm_msg += "  - No PII or prompt injection detected.\n"
        confirm_msg += "Routing to downstream LLM Risk Review."
        
        yield Event(
            content=types.Content(
                role="model", parts=[types.Part.from_text(text=confirm_msg)]
            )
        )
        yield Event(
            output=node_input,
            actions=EventActions(
                route="clean",
                state_delta=state_delta
            )
        )


@node(rerun_on_resume=True)
async def manual_review(
    ctx: Context, node_input: ExpenseReport
) -> AsyncGenerator[Event | RequestInput, None]:
    """Prompts human for approval when downstream LLM is bypassed due to a security event."""
    # 1. Display security warning if not already shown
    if "risk_analysis" not in ctx.state:
        ctx.state["risk_analysis"] = (
            "⚠️ **SECURITY ALERT**: Prompt injection attempt detected in expense description. "
            "Downstream LLM review bypassed to protect model and logs."
        )

    # Yield the security warning to the interface
    yield Event(
        content=types.Content(
            role="model",
            parts=[
                types.Part.from_text(
                    text=(
                        f"🚨🔴 **MANUAL REVIEW REQUIRED (SECURITY EXCEPTION)** 🔴🚨\n\n"
                        f"**WARNING**: This expense report was flagged for potential prompt injection "
                        f"and has bypassed LLM automated review.\n\n"
                        f"**Scrubbed Description**: \"*{node_input.description}*\"\n\n"
                        f"Please review manually with extreme caution."
                    )
                )
            ],
        )
    )

    # 2. Pause and prompt for human review input
    if not ctx.resume_inputs or "approval_decision" not in ctx.resume_inputs:
        yield RequestInput(
            interrupt_id="approval_decision",
            message="Please review the security warning above. Do you approve this expense despite the security flag? (Reply 'approve' or 'reject')",
        )
        return

    # 3. Human has responded, retrieve decision from context
    raw_decision = ctx.resume_inputs["approval_decision"]
    if isinstance(raw_decision, dict):
        decision_str = (
            raw_decision.get("output")
            or raw_decision.get("response")
            or raw_decision.get("approval_decision")
            or str(raw_decision)
        )
    else:
        decision_str = str(raw_decision)

    decision = decision_str.strip().lower()
    approved = any(word in decision for word in ["approve", "yes", "y", "ok"])

    outcome = {
        "status": "APPROVED" if approved else "REJECTED",
        "reason": "Human reviewed security exception manually",
        "risk_analysis": ctx.state.get("risk_analysis"),
        "security_event": True,
        "approved_at": datetime.datetime.now().isoformat(),
        "expense": node_input.model_dump(),
    }

    message = (
        f"📝 **Security Review Recorded**:\n"
        f"  - Decision: `{'APPROVED' if approved else 'REJECTED'}`\n"
        f"  - Decision logic: {outcome['reason']}\n"
        f"  - Recorded at: `{outcome['approved_at']}`"
    )
    yield Event(
        content=types.Content(role="model", parts=[types.Part.from_text(text=message)])
    )
    yield Event(output=outcome, actions=EventActions(state_delta={"outcome": outcome}))


# Setup the ADK 2.0 Graph Workflow
root_agent = Workflow(
    name="ambient_expense_workflow",
    edges=[
        ("START", extract_expense),
        Edge(from_node=extract_expense, to_node=auto_approve, route="auto_approve"),
        Edge(from_node=extract_expense, to_node=security_checkpoint, route="llm_review"),
        Edge(from_node=security_checkpoint, to_node=llm_review, route="clean"),
        Edge(from_node=security_checkpoint, to_node=manual_review, route="security_alert"),
    ],
    description="Graph-based ambient expense approval agent with model risk assessment and human-in-the-loop.",
)

# Container Application required by ADK CLI and playground
app = App(
    root_agent=root_agent,
    name="expense_agent",
)
