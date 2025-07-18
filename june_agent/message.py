from dataclasses import dataclass, asdict, field
from typing import Optional

@dataclass
class Message:
    """
    Represents a single message in a conversation.
    """
    role: str
    content: str
    tool_call_id: Optional[str] = field(default=None, kw_only=True)

    def as_dict(self):
        """
        Returns a dictionary representation of the message.
        """
        return {k: v for k, v in asdict(self).items() if v is not None}
