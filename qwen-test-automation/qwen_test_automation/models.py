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


@dataclass
class TestScenario:
    id: str
    feature: str
    group: str
    screen: str
    title: str
    precondition: str
    steps: list[str]
    expected_result: str
    applicable_platforms: list[str]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "feature": self.feature,
            "group": self.group,
            "screen": self.screen,
            "title": self.title,
            "precondition": self.precondition,
            "steps": list(self.steps),
            "expected_result": self.expected_result,
            "applicable_platforms": list(self.applicable_platforms),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TestScenario":
        return cls(
            id=data["id"],
            feature=data["feature"],
            group=data["group"],
            screen=data["screen"],
            title=data["title"],
            precondition=data["precondition"],
            steps=list(data["steps"]),
            expected_result=data["expected_result"],
            applicable_platforms=list(data["applicable_platforms"]),
        )


def to_testcase(scenario: TestScenario, platform: str) -> TestCase:
    if platform not in scenario.applicable_platforms:
        raise ValueError(f"platform {platform} not applicable to scenario {scenario.id}")
    return TestCase(
        id=f"{scenario.id}-{platform}",
        feature=scenario.title,
        precondition=scenario.precondition,
        steps=list(scenario.steps),
        expected_result=scenario.expected_result,
        platform=platform,
    )
