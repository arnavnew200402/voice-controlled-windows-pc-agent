"""Experimental ChatGPT-plan text path and separate UI sandbox."""

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="Experimental Windows agent foundation")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--ui", action="store_true", help="Open the limited online Windows preview")
    mode.add_argument("--ui-demo", action="store_true", help="Open the sandbox-only notch studio")
    mode.add_argument("--login", action="store_true", help="Sign in with ChatGPT in your browser")
    mode.add_argument("--text", metavar="REQUEST", help="Run one text request")
    parser.add_argument(
        "--provider",
        choices=("chatgpt", "ollama"),
        default="chatgpt",
        help="ChatGPT plan by default; Ollama is experimental",
    )
    parser.add_argument(
        "--model", default="", help="Provider model; ChatGPT defaults to the first available model"
    )
    parser.add_argument(
        "--ollama-port", type=int, default=11434, help="Local Ollama port (loopback only)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not launch a real application")
    args = parser.parse_args()
    if args.ui or args.ui_demo:
        try:
            from vox.ui.app import run_demo, run_live
        except ImportError as exc:
            parser.exit(1, f"UI dependencies missing: {exc}. Install with pip install '.[ui]'\n")
        raise SystemExit(run_live() if args.ui else run_demo())
    if args.login:
        from vox.agent.auth_storage import StorageError, windows_store
        from vox.agent.chatgpt_auth import AuthError, sign_in

        try:
            sign_in(windows_store())
        except (AuthError, StorageError) as exc:
            parser.exit(1, f"ChatGPT sign-in failed: {exc}\n")
        print("ChatGPT sign-in completed. Credentials are protected by Windows DPAPI.")
        return
    if args.text is not None:
        from vox.agent.provider import ChatProvider
        from vox.agent.tools import DryRunBackend, ToolRegistry
        from vox.agent.turn import run_turn
        from vox.agent.windows import WindowsNotepadBackend

        if args.provider == "ollama":
            from vox.agent.ollama import LoopbackTransport, OllamaProvider

            model = args.model or os.environ.get("OLLAMA_MODEL", "")
            if not model.strip():
                parser.exit(2, "Set --model or OLLAMA_MODEL to an installed tool-calling model.\n")
            try:
                provider: ChatProvider = OllamaProvider(
                    model, LoopbackTransport(port=args.ollama_port)
                )
            except ValueError as exc:
                parser.exit(2, f"Invalid local model configuration: {exc}\n")
        else:
            from vox.agent.auth_storage import StorageError, windows_store
            from vox.agent.chatgpt import ChatGPTProvider

            try:
                _, session = windows_store().load()
            except StorageError as exc:
                parser.exit(1, f"ChatGPT sign-in unavailable: {exc}\n")
            if session is None:
                parser.exit(1, "Sign in first with: python -m vox --login\n")
            import time

            if time.time() >= session.expires_at - 30:
                parser.exit(
                    1, "ChatGPT session expired; sign in again with: python -m vox --login\n"
                )
            try:
                provider = ChatGPTProvider(session, args.model)
            except ValueError:
                parser.exit(2, "Invalid ChatGPT model configuration.\n")
        backend = DryRunBackend() if args.dry_run else WindowsNotepadBackend()
        result = run_turn(args.text, provider, ToolRegistry(backend))
        print(result.evidence)
        raise SystemExit(0 if result.ok else 1)
    print(
        "Experimental agent: use --login for ChatGPT, --text for Notepad, or --ui-demo for the sandbox."
    )


if __name__ == "__main__":
    main()
