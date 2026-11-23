from dataclasses import dataclass

VALID_PLATFORMS = frozenset({"WTS", "MWTS", "MTS-Android", "MTS-iOS"})


@dataclass
class TestCase:
    id: str
    feature: str
    precondition: str
    steps: list[str]
    expected_result: str
    platform: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "feature": self.feature,
            "precondition": self.precondition,
            "steps": list(self.steps),
            "expected_result": self.expected_result,
            "platform": self.platform,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TestCase":
        return cls(
            id=data["id"],
            feature=data["feature"],
            precondition=data["precondition"],
            steps=list(data["steps"]),
            expected_result=data["expected_result"],
            platform=data["platform"],
        )
