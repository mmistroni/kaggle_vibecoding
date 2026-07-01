from google.adk import Agent, Context, Workflow
from google.adk.workflow import node

# 1. Define the classifier agent to categorize queries
classifier_agent = Agent(
    model="gemini-3.5-flash",
    name="classifier_agent",
    description="Classifies user queries into shipping-related or unrelated.",
    instruction=(
        "You are an AI classifier for a shipping company.\n"
        "Analyze the user query. Classify it into one of these two categories:\n"
        '- "shipping": if the query is related to shipping rates, shipping prices, package tracking, delivery status, shipping duration, returns, refunds, or mailing services.\n'
        '- "unrelated": if the query is about unrelated topics like cooking, general science, coding, history, other companies, greetings, general chit-chat, etc.\n\n'
        'Output exactly "shipping" or "unrelated". Do not write any other explanation or words.'
    ),
)

# 2. Define the shipping FAQ agent to handle shipping queries
shipping_faq_agent = Agent(
    model="gemini-3.5-flash",
    name="shipping_faq_agent",
    description="Answers shipping-related customer support queries.",
    instruction=(
        "You are a super playful, highly enthusiastic, and friendly customer support representative for a shipping company! ✨\n"
        "The user has asked a query related to shipping (such as rates, tracking, delivery, or returns).\n"
        "Answer their question clearly with tons of positive energy and helpful emojis! 📦🚚🎉\n"
        "When answering queries about shipping rates, be sure to enthusiastically highlight that we offer **FREE SHIPPING** on all orders over **$50**! 🚀✨\n"
        "Use lists and bullet points if helpful to keep the information super structured, easy to read, and exciting to look at! Keep that premium, delightful, and ultra-enthusiastic vibe going! 🌟"
    ),
)

# 3. Define the decline agent to handle unrelated queries
decline_agent = Agent(
    model="gemini-3.5-flash",
    name="decline_agent",
    description="Politely declines unrelated queries.",
    instruction=(
        "You are a customer support representative for a shipping company.\n"
        "The user has asked a query that is not related to shipping. Politely decline to answer the query.\n"
        "Explain that as a shipping assistant, you can only help with shipping-related inquiries such as shipping rates, "
        "package tracking, delivery schedules, and returns/refunds. Suggest that they ask a shipping-related question."
    ),
)


# 4. Define the routing/classification workflow node
@node(name="classifier_node", rerun_on_resume=True)
async def classifier_node(ctx: Context, node_input: str) -> str:
    # Run the classifier agent dynamically on the user query
    classification = await ctx.run_node(classifier_agent, node_input=node_input)
    classification_str = str(classification).strip().lower()

    # Set the route based on classification
    if "unrelated" in classification_str:
        ctx.route = "unrelated"
    elif "shipping" in classification_str:
        ctx.route = "shipping"
    else:
        # Robust fallback
        ctx.route = "unrelated"

    # Return the original user query so downstream nodes receive it as their input
    return node_input


# 5. Define the graph workflow
root_agent = Workflow(
    name="customer_support_workflow",
    description="A graph-based customer support workflow for a shipping company.",
    edges=[
        ("START", classifier_node),
        (
            classifier_node,
            {
                "shipping": shipping_faq_agent,
                "unrelated": decline_agent,
            },
        ),
    ],
)

from google.adk.apps import App

app = App(root_agent=root_agent, name="customer_support_agent")
