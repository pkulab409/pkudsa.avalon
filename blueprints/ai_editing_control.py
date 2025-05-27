# ai_editing_control.py


class AIEditingControl:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AIEditingControl, cls).__new__(cls)
            cls._instance.ai_editing_allowed = True
        return cls._instance

    def allow_ai_editing(self):
        self.ai_editing_allowed = True

    def freeze_ai_editing(self):
        self.ai_editing_allowed = False

    def is_ai_editing_allowed(self):
        return self.ai_editing_allowed


# Global instance
ai_editing_control = AIEditingControl()
