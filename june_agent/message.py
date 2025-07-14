from dataclasses import dataclass, asdict

@dataclass
class Message:
    """
    Represents a single message in a conversation.
    """
    role: str
    content: str

    def as_dict(self):
        """
        Returns a dictionary representation of the message.
        """
        return asdict(self)
