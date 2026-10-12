if __name__ == "__main__":
    import sys
    try:
        from frm.app import main
        main()
    except Exception:
        # Startup/import failures must also be machine-readable in frozen smoke tests.
        if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
            import json
            from pathlib import Path
            import traceback
            report = Path(sys.argv[2])
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps({"ok": False, "error": traceback.format_exc()}), encoding="utf-8")
            sys.exit(1)
        raise
