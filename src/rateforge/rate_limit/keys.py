class RateLimitKeyBuilder:
    PREFIX = "rateforge"

    @classmethod
    def build(
        cls,
        identity: str,
        endpoint: str,
    ) -> str:
        return f"{cls.PREFIX}:{identity}:{endpoint}"