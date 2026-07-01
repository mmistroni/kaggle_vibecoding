import os


class Config:
    # Dollar threshold below which auto-approval happens instantly
    THRESHOLD: float = float(os.getenv("EXPENSE_THRESHOLD", 100.0))

    # Model used only for the risk analysis (LLM review) step
    MODEL_NAME: str = os.getenv("EXPENSE_MODEL", "gemini-3.1-flash-lite")


CONFIG = Config()
