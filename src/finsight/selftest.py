"""End-to-end self-test (no GUI) — `finsight --selftest`.

Verifies the full stack on the target machine in ~30 seconds: demo data,
KPIs, executive brief, NLQ, analytics, reconciliation, Excel tools, MIS
generation, automation jobs, and backup. Run it after installing on a
new laptop; if every line says OK, the desktop app will work.
"""

from __future__ import annotations

import sys
import tempfile
import traceback
from collections.abc import Callable
from pathlib import Path

import pandas as pd


def run_selftest() -> int:
    """Execute every subsystem once; return 0 when all pass."""
    from .core.config import AppConfig
    from .ui.context import build_context

    checks: list[tuple[str, Callable[[], str]]] = []
    config = AppConfig()
    config.demo.loans = 300  # keep the self-test snappy

    from .data.demo_data import generate_demo_db

    with tempfile.TemporaryDirectory(
        prefix="finsight-selftest-", ignore_cleanup_errors=True
    ) as tmp:
        tmp_path = Path(tmp)
        demo = generate_demo_db(config.demo, path=tmp_path / "demo.db", force=True)

        context = build_context(config)
        context.connections.save(
            __import__("finsight.core.appdb", fromlist=["SavedConnection"]).SavedConnection(
                name="SelfTest DB", kind="sqlite", params={"path": str(demo.path)}
            )
        )
        context.use_connection("SelfTest DB")

        checks.append(("demo data", lambda: f"{demo.loans} loans, {demo.payments} payments"))
        checks.append(
            ("KPIs", lambda: f"portfolio {context.data.kpis().portfolio_outstanding:,.0f}")
        )
        checks.append(("executive brief", lambda: context.executive.brief().health.grade))
        checks.append(("branch ranking", lambda: f"{len(context.data.branch_summary())} branches"))
        checks.append(("NLQ", lambda: context.nlq.ask("top 3 branches by overdue").intent))
        checks.append(
            ("forecast", lambda: f"{context.analytics.collections_forecast().expected_total:,.0f}")
        )
        checks.append(
            ("anomalies", lambda: context.analytics.collection_anomalies().explanation[:40])
        )
        checks.append(
            ("segments", lambda: f"{len(context.analytics.customer_segments().profile)} segments")
        )
        checks.append(
            ("risk scores", lambda: f"{len(context.analytics.loan_risk_scores().frame)} scored")
        )

        def check_recon() -> str:
            from .modules.recon import reconcile

            left = pd.DataFrame({"utr": ["A1", "A2", "A3"], "amount": [100.0, 200.0, 300.0]})
            right = pd.DataFrame({"utr": ["A1", "A2", "A4"], "amount": [100.0, 250.0, 50.0]})
            result = reconcile(left, right, key="utr", amount="amount")
            return result.summary

        checks.append(("reconciliation", check_recon))

        def check_excel() -> str:
            from .modules.excel_tools import clean, read_table, sql_to_excel

            frame = pd.DataFrame({"Name ": [" a", "b ", " a"], "Val": [1, 2, 1]})
            report = clean(frame)
            out = sql_to_excel(report.frame, tmp_path / "clean.xlsx")
            return f"{len(read_table(out))} rows, {len(report.actions)} action(s)"

        checks.append(("excel tools", check_excel))

        def check_mis() -> str:
            output = context.mis.generate("daily", out_dir=tmp_path)
            return output.excel_path.name

        checks.append(("MIS pack", check_mis))

        def check_automation() -> str:
            context.automation.register_job("selftest", lambda: "ok")
            return context.automation.run_job("selftest")

        checks.append(("automation job", check_automation))

        def check_backup() -> str:
            from .core.backup import create_backup

            return create_backup().name

        checks.append(("backup", check_backup))

        def check_data_quality() -> str:
            from .modules.data_quality import profile_frame

            frame = pd.DataFrame(
                {
                    "id": [1, 2, 2, 4, 5],
                    "amount": [100.0, 200.0, 200.0, None, 100000.0],
                    "name": ["A", "B ", "b", "C", "A"],
                }
            )
            report = profile_frame(frame)
            return f"score {report.score:.0f}/{report.grade}, {len(report.issues)} issue(s)"

        checks.append(("data quality", check_data_quality))

        def check_api_explorer() -> str:
            from .modules.api_explorer import ApiExplorer, ApiRequest

            class _FakeResponse:
                status_code = 200
                reason = "OK"
                ok = True
                headers = {"Content-Type": "application/json"}
                content = b'{"pong": true}'
                text = '{"pong": true}'

            class _FakeSession:
                def request(self, **_kwargs: object) -> _FakeResponse:
                    return _FakeResponse()

            api = ApiExplorer(session=_FakeSession())
            response = api.send(ApiRequest(method="GET", url="https://api.test/ping"))
            return (
                f"{response.status_code} in {response.elapsed_ms:.0f}ms, {len(api.history)} logged"
            )

        checks.append(("api explorer", check_api_explorer))

        def check_plugins() -> str:
            return f"{len(context.registry.plugins)} plugin(s) discovered"

        checks.append(("plugins", check_plugins))

        def check_mis_builder() -> str:
            from .modules.mis_builder import BuilderConfig, build_pivot, export_pivot
            from .modules.mis_samples import sample_lending_dataset

            sample = sample_lending_dataset(200)
            result = build_pivot(
                sample, BuilderConfig(group_by="branch", value="loan_amount", aggregate="Sum")
            )
            assert str(result.frame.iloc[-1, 0]) == "TOTAL"
            out = export_pivot(result, tmp_path / "builder.xlsx")
            assert out.is_file()
            return f"{len(result.frame) - 1} groups · {result.title}"

        checks.append(("mis builder", check_mis_builder))

        def check_mis_templates() -> str:
            from .modules.mis_samples import sample_lending_dataset
            from .modules.mis_templates import TEMPLATES, export_template, run_template

            sample = sample_lending_dataset(200)
            results = [run_template(key, sample) for key in TEMPLATES]
            out = export_template(results[0], tmp_path / "template.xlsx")
            assert out.is_file() and all(r.kpis for r in results)
            return f"{len(results)} templates OK"

        checks.append(("mis templates", check_mis_templates))

        def check_auto_reporter() -> str:
            from datetime import datetime

            from .modules.auto_reporter import AutoReporter, ReportJob
            from .modules.mis_samples import sample_lending_dataset

            source = tmp_path / "auto_source.csv"
            sample_lending_dataset(120).to_csv(source, index=False)
            reporter = AutoReporter(store_path=tmp_path / "auto_jobs.json", output_dir=tmp_path)
            job = reporter.add_job(
                ReportJob(
                    name="Selftest Report",
                    kind="template:portfolio_health",
                    source_path=str(source),
                    frequency="Daily",
                    at="23:59",
                ),
                now=datetime(2026, 1, 1, 8, 0),
            )
            fired = reporter.run_due_jobs(now=datetime(2026, 1, 2, 0, 0))
            assert len(fired) == 1 and fired[0].is_file()
            return f"fired 1 job · next {job.next_run}"

        checks.append(("auto reporter", check_auto_reporter))

        print("FinSight self-test")
        print("=" * 60)
        failures = 0
        for name, check in checks:
            try:
                detail = check()
                print(f"  OK   {name:<18} {detail}")
            except Exception as exc:
                failures += 1
                print(f"  FAIL {name:<18} {exc}")
                traceback.print_exc()
        print("=" * 60)
        print(
            "ALL CHECKS PASSED — FinSight is ready. Run `finsight` to launch."
            if failures == 0
            else f"{failures} check(s) FAILED — see traceback above."
        )
        # Release every handle before the temp dir is removed — on Windows
        # an open SQLite file cannot be deleted (caught by CI on windows-latest).
        context.connections.dispose_all()
        context.runner.shutdown()
        context.appdb.close()
        return 0 if failures == 0 else 1


def main() -> int:
    """Console entry point: `finsight [--selftest]`."""
    if "--selftest" in sys.argv:
        return run_selftest()
    from .app import main as gui_main

    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())
