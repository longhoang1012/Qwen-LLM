import argparse

from qwen_test_automation.llm.ollama_client import OllamaClient
from qwen_test_automation.ingestion.pipeline import run_ingestion


def main():
    parser = argparse.ArgumentParser(prog="cli.py")
    subparsers = parser.add_subparsers(dest="command", required=True)

    gen = subparsers.add_parser(
        "generate-scenarios",
        help="Đọc 1 file (PDF/txt/md/ảnh) và sinh testcase Excel theo chuẩn QC",
    )
    gen.add_argument("doc_path", help="Đường dẫn file đầu vào (.pdf/.txt/.md/.png/.jpg/.jpeg)")
    gen.add_argument("out_path", help="Đường dẫn file Excel sẽ ghi ra")
    gen.add_argument("--text-model", default="qwen2.5:7b")
    gen.add_argument("--vision-model", default="qwen2.5vl:7b")
    gen.add_argument("--ollama-url", default="http://localhost:11434")
    gen.add_argument(
        "--timeout", type=int, default=120,
        help="Số giây chờ Ollama trả lời trước khi báo timeout (mặc định 120)",
    )

    args = parser.parse_args()

    if args.command == "generate-scenarios":
        client = OllamaClient(base_url=args.ollama_url, timeout=args.timeout)
        scenarios = run_ingestion(
            args.doc_path, args.out_path, client,
            text_model=args.text_model, vision_model=args.vision_model,
        )
        print(f"Wrote {len(scenarios)} scenario(s) to {args.out_path}")


if __name__ == "__main__":
    main()
