from qwen_test_automation.ingestion.doc_reader import read_input
from qwen_test_automation.ingestion.scenario_generator import generate_scenarios
from qwen_test_automation.ingestion.excel_export import export_scenarios_to_excel


def run_ingestion(doc_path, out_path, client, text_model, vision_model):
    parsed = read_input(doc_path)
    model = vision_model if parsed["images"] else text_model
    scenarios = generate_scenarios(
        parsed["text"], client=client, model=model, images=parsed["images"] or None
    )
    export_scenarios_to_excel(scenarios, out_path)
    return scenarios
