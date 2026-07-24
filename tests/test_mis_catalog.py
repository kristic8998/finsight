"""Tests: MIS report catalog, custom templates, branding, recent reports."""

from __future__ import annotations

import pandas as pd
import pytest

from finsight.modules.mis import MisGenerator
from finsight.modules.mis_catalog import CatalogError, MisCatalog


@pytest.fixture()
def catalog(data, appdb):
    return MisCatalog(data, appdb, company_name="Acme Lending Ltd")


class TestCatalogReports:
    @pytest.mark.parametrize(
        "report_id", ["collections", "disbursement", "recovery", "branch", "employee", "product"]
    )
    def test_every_report_builds_xlsx(self, catalog, tmp_path, report_id):
        output = catalog.build(report_id, days=60, fmt="xlsx", out_dir=tmp_path)
        assert output.paths[0].exists()
        sheets = pd.read_excel(output.paths[0], sheet_name=None)
        assert len(sheets) == len(output.sheets)
        # Branding + title stamped in A1 of the first sheet.
        first = next(iter(sheets.values()))
        assert "Acme Lending Ltd" in str(first.columns[0])

    def test_csv_format_writes_one_file_per_section(self, catalog, tmp_path):
        output = catalog.build("collections", days=30, fmt="csv", out_dir=tmp_path)
        assert len(output.paths) == len(output.sheets)
        assert all(p.suffix == ".csv" and p.exists() for p in output.paths)
        frame = pd.read_csv(output.paths[0])
        assert not frame.empty

    def test_collections_report_has_expected_sections(self, catalog, tmp_path):
        output = catalog.build("collections", days=45, fmt="xlsx", out_dir=tmp_path)
        assert set(output.sheets) == {
            "KPI Summary",
            "Collections by Day",
            "Collections by Branch",
            "Collections by Mode",
        }
        assert output.sheets["Collections by Day"] == 46  # inclusive window

    def test_unknown_report_and_format_raise(self, catalog, tmp_path):
        with pytest.raises(CatalogError):
            catalog.build("payroll", out_dir=tmp_path)
        with pytest.raises(CatalogError):
            catalog.build("branch", fmt="docx", out_dir=tmp_path)


class TestTemplates:
    def test_save_build_delete_roundtrip(self, catalog, tmp_path):
        catalog.save_template("My Morning Pack", ["kpi_summary", "branch_ranking"])
        assert "My Morning Pack" in catalog.templates()

        output = catalog.build_from_template(
            "My Morning Pack", days=30, fmt="xlsx", out_dir=tmp_path
        )
        sheets = pd.read_excel(output.paths[0], sheet_name=None)
        assert set(sheets) == {"KPI Summary", "Branch Ranking"}

        catalog.delete_template("My Morning Pack")
        assert "My Morning Pack" not in catalog.templates()

    def test_template_validation(self, catalog):
        with pytest.raises(CatalogError):
            catalog.save_template("", ["kpi_summary"])
        with pytest.raises(CatalogError):
            catalog.save_template("x", [])
        with pytest.raises(CatalogError):
            catalog.save_template("x", ["not_a_section"])
        with pytest.raises(CatalogError):
            catalog.build_from_template("never saved")

    def test_templates_persist_in_appdb(self, data, appdb):
        first = MisCatalog(data, appdb)
        first.save_template("persisted", ["product_mix"])
        second = MisCatalog(data, appdb)  # fresh instance, same store
        assert second.templates()["persisted"] == ["product_mix"]


class TestBranding:
    def test_pack_carries_company_name(self, executive, tmp_path):
        generator = MisGenerator(executive, company_name="Acme Lending Ltd")
        output = generator.generate("daily", out_dir=tmp_path)
        html = output.html_path.read_text(encoding="utf-8")
        assert "Acme Lending Ltd ·" in html

    def test_pack_without_branding_unchanged(self, executive, tmp_path):
        generator = MisGenerator(executive)
        output = generator.generate("daily", out_dir=tmp_path)
        html = output.html_path.read_text(encoding="utf-8")
        assert "None ·" not in html and " · Daily" not in html
