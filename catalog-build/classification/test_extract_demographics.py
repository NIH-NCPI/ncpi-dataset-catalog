"""Tests for extract_demographics.py."""

import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import extract_demographics as ed

# ---------------------------------------------------------------------------
# Stub XML fragments
# ---------------------------------------------------------------------------

SUBJECT_PHENOTYPES_XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <data_table name="Test_Subject_Phenotypes"
                dataset_id="pht000123.v1"
                study_name="Test Study Alpha"
                study_id="phs000001.v1"
                participant_set="1">
      <variable id="phv00000001.v1.p1" var_name="SUBJID" calculated_type="string">
        <description>Subject ID</description>
        <total><stats><stat n="100" nulls="0"/></stats></total>
      </variable>
      <variable id="phv00000002.v1.p1" var_name="SEX" calculated_type="enum_integer">
        <description>Sex of participant</description>
        <total><stats>
          <stat n="100" nulls="0"/>
          <enum code="1" count="55">Male</enum>
          <enum code="2" count="45">Female</enum>
        </stats></total>
      </variable>
      <variable id="phv00000002.v1.p1.c1" var_name="SEX" calculated_type="enum_integer">
        <description>Sex of participant</description>
        <total><stats>
          <stat n="80" nulls="0"/>
          <enum code="1" count="44">Male</enum>
          <enum code="2" count="36">Female</enum>
        </stats></total>
      </variable>
      <variable id="phv00000003.v1.p1" var_name="RACE" calculated_type="enum_integer">
        <description>Race</description>
        <total><stats>
          <stat n="100" nulls="5"/>
          <enum code="1" count="60">White</enum>
          <enum code="2" count="30">Black or African American</enum>
          <enum code="3" count="10">Asian</enum>
        </stats></total>
      </variable>
      <variable id="phv00000004.v1.p1" var_name="AGE" calculated_type="integer">
        <description>Age at enrollment</description>
        <total><stats><stat n="100" nulls="0" mean="55.2" min="18" max="89"/></stats></total>
      </variable>
    </data_table>
""")

MULTI_SEX_XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <data_table name="Multi_Subject_Phenotypes"
                dataset_id="pht000456.v1"
                study_name="Multi Variable Study"
                study_id="phs000002.v1"
                participant_set="1">
      <variable id="phv00000010.v1.p1" var_name="gender" calculated_type="enum_integer">
        <description>Gender (subset)</description>
        <total><stats>
          <stat n="50" nulls="10"/>
          <enum code="M" count="30">Male</enum>
          <enum code="F" count="20">Female</enum>
        </stats></total>
      </variable>
      <variable id="phv00000011.v1.p1" var_name="Sex" calculated_type="enum_integer">
        <description>Biological sex</description>
        <total><stats>
          <stat n="200" nulls="0"/>
          <enum code="1" count="110">Male</enum>
          <enum code="2" count="90">Female</enum>
        </stats></total>
      </variable>
    </data_table>
""")

NO_DEMOGRAPHICS_XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <data_table name="Empty_Subject_Phenotypes"
                dataset_id="pht000789.v1"
                study_name="No Demographics Study"
                study_id="phs000003.v1"
                participant_set="1">
      <variable id="phv00000020.v1.p1" var_name="SUBJID" calculated_type="string">
        <description>Subject ID</description>
        <total><stats><stat n="50" nulls="0"/></stats></total>
      </variable>
    </data_table>
""")

SEX_NO_ENUMS_XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <data_table name="NoEnum_Subject_Phenotypes"
                dataset_id="pht000999.v1"
                study_name="No Enum Study"
                study_id="phs000004.v1"
                participant_set="1">
      <variable id="phv00000030.v1.p1" var_name="SEX" calculated_type="integer">
        <description>Sex coded as integer</description>
        <total><stats><stat n="75" nulls="0" mean="1.4" min="1" max="2"/></stats></total>
      </variable>
    </data_table>
""")

DBGAP_CSV_CONTENT = textwrap.dedent("""\
    accession,name,description,Parent study,Study Disease/Focus,Study Design,Study Markerset,Study Molecular Data Type,Study Content,Ancestry (computed),NIH Institute,Study Consent,Release Date,Embargo Release Date,Related Terms,Collections
    phs000001.v1.p1,Test Study Alpha,A test study,,,,,,,"European (60), African American (30), East Asian (10)",,,,,,
    phs000005.v1.p1,Ancestry Only Study,No XML,,,,,,,"Hispanic2 (100), European (50)",,,,,,
    phs000006.v1.p1,No Ancestry Study,Empty ancestry,,,,,,,,,,,,,
""")


# ---------------------------------------------------------------------------
# Fixture: tmp directory tree with patched module paths
# ---------------------------------------------------------------------------


@pytest.fixture
def study_tree(tmp_path):
    """Create a temporary directory tree mimicking the dbGaP source layout."""
    dbgap_dir = tmp_path / "source" / "dbgap-variables"

    s1 = dbgap_dir / "phs000001"
    s1.mkdir(parents=True)
    (s1 / "phs000001.v1.pht000123.v1.p1.Test_Subject_Phenotypes.var_report.xml").write_text(
        SUBJECT_PHENOTYPES_XML
    )

    s2 = dbgap_dir / "phs000002"
    s2.mkdir()
    (s2 / "phs000002.v1.pht000456.v1.p1.Multi_Subject_Phenotypes.var_report.xml").write_text(
        MULTI_SEX_XML
    )

    s3 = dbgap_dir / "phs000003"
    s3.mkdir()
    (s3 / "phs000003.v1.pht000789.v1.p1.Empty_Subject_Phenotypes.var_report.xml").write_text(
        NO_DEMOGRAPHICS_XML
    )

    s4 = dbgap_dir / "phs000004"
    s4.mkdir()
    (s4 / "phs000004.v1.pht000999.v1.p1.NoEnum_Subject_Phenotypes.var_report.xml").write_text(
        SEX_NO_ENUMS_XML
    )

    s99 = dbgap_dir / "phs000099"
    s99.mkdir()
    (s99 / "phs000099.v1.pht009999.v1.p1.Other_Table.var_report.xml").write_text(
        "<data_table/>"
    )

    csv_path = tmp_path / "source" / "dbgap-advanced-search.csv"
    csv_path.write_text(DBGAP_CSV_CONTENT)

    original_vars_dir = ed.DBGAP_VARIABLES_DIR
    original_csv = ed.DBGAP_CSV
    ed.DBGAP_VARIABLES_DIR = dbgap_dir
    ed.DBGAP_CSV = csv_path
    yield tmp_path
    ed.DBGAP_VARIABLES_DIR = original_vars_dir
    ed.DBGAP_CSV = original_csv


# ===========================================================================
# Unit tests: pure functions (no filesystem needed)
# ===========================================================================


class TestIsConsentVariant:
    def test_non_consent(self):
        assert ed.is_consent_variant("phv00000002.v1.p1") is False

    def test_consent_c1(self):
        assert ed.is_consent_variant("phv00000002.v1.p1.c1") is True

    def test_consent_c2(self):
        assert ed.is_consent_variant("phv00084446.v2.p3.c2") is True

    def test_short_id(self):
        assert ed.is_consent_variant("phv00000002") is False

    def test_empty(self):
        assert ed.is_consent_variant("") is False


class TestClassifyVariableName:
    @pytest.mark.parametrize("name,expected", [
        ("SEX", (True, False)),
        ("sex", (True, False)),
        ("Sex", (True, False)),
        ("GENDER", (True, False)),
        ("gender", (True, False)),
        ("Gender", (True, False)),
        ("sex_selfreport", (True, False)),
        ("demographic.gender", (True, False)),
        ("GENDERNUM", (True, False)),
        ("RACE", (False, True)),
        ("race", (False, True)),
        ("Race", (False, True)),
        ("ETHNICITY", (False, True)),
        ("ethnicity", (False, True)),
        ("dem_race", (False, True)),
        ("RACE_ETHNICITY", (False, True)),
        ("Hispanic_Ethnicity", (False, True)),
        ("AGE", (False, False)),
        ("SUBJID", (False, False)),
        ("BMI", (False, False)),
        ("CONSENT", (False, False)),
        ("DIAGNOSIS", (False, False)),
    ])
    def test_classification(self, name, expected):
        assert ed.classify_variable_name(name) == expected


class TestParseAncestryString:
    def test_standard_format(self):
        raw = "European (60), African American (30), East Asian (10)"
        result = ed.parse_ancestry_string(raw)
        assert result == [
            {"count": 60, "label": "European"},
            {"count": 30, "label": "African American"},
            {"count": 10, "label": "East Asian"},
        ]

    def test_sorted_by_count_descending(self):
        raw = "East Asian (5), European (100), African (20)"
        result = ed.parse_ancestry_string(raw)
        assert result[0]["count"] == 100
        assert result[1]["count"] == 20
        assert result[2]["count"] == 5

    def test_single_category(self):
        raw = "European (500)"
        result = ed.parse_ancestry_string(raw)
        assert len(result) == 1
        assert result[0] == {"count": 500, "label": "European"}

    def test_empty_string(self):
        assert ed.parse_ancestry_string("") == []

    def test_real_world_format(self):
        raw = "Other (15), East Asian (20), Hispanic2 (146), Other Asian or Pacific Islander (20), European (60932)"
        result = ed.parse_ancestry_string(raw)
        assert result[0] == {"count": 60932, "label": "European"}
        assert len(result) == 5

    def test_label_with_spaces(self):
        raw = "Other Asian or Pacific Islander (42)"
        result = ed.parse_ancestry_string(raw)
        assert result[0]["label"] == "Other Asian or Pacific Islander"


class TestSelectBestVariable:
    def test_empty_list(self):
        assert ed.select_best_variable([]) is None

    def test_single_variable(self):
        dist = ed.VariableDistribution(
            categories=[], dataset_id="d", n=100, name="a",
            nulls=0, table_name="t", variable_id="v1",
        )
        assert ed.select_best_variable([dist]) is dist

    def test_picks_highest_n(self):
        low = ed.VariableDistribution(
            categories=[], dataset_id="d", n=50, name="low",
            nulls=0, table_name="t", variable_id="v1",
        )
        high = ed.VariableDistribution(
            categories=[], dataset_id="d", n=200, name="high",
            nulls=0, table_name="t", variable_id="v2",
        )
        assert ed.select_best_variable([low, high]).name == "high"

    def test_tiebreak_by_nulls(self):
        more_nulls = ed.VariableDistribution(
            categories=[], dataset_id="d", n=100, name="more_nulls",
            nulls=10, table_name="t", variable_id="v1",
        )
        fewer_nulls = ed.VariableDistribution(
            categories=[], dataset_id="d", n=100, name="fewer_nulls",
            nulls=5, table_name="t", variable_id="v2",
        )
        assert ed.select_best_variable([more_nulls, fewer_nulls]).name == "fewer_nulls"


class TestDistributionToDict:
    def test_output_keys(self):
        dist = ed.VariableDistribution(
            categories=[{"code": "1", "count": 50, "label": "Male"}],
            dataset_id="pht000123.v1",
            n=50,
            name="SEX",
            nulls=0,
            table_name="Subject_Phenotypes",
            variable_id="phv00000001.v1.p1",
        )
        result = ed.distribution_to_dict(dist)
        assert list(result.keys()) == [
            "categories", "datasetId", "n", "nulls",
            "tableName", "variableId", "variableName",
        ]
        assert result["variableName"] == "SEX"
        assert result["n"] == 50
        assert result["datasetId"] == "pht000123.v1"


class TestExtractDistribution:
    """Unit tests for extract_distribution using in-memory XML elements."""

    def _make_variable(self, xml_str):
        return ET.fromstring(xml_str)

    def test_extracts_enums(self):
        var = self._make_variable("""
            <variable id="phv001.v1.p1" var_name="SEX">
              <total><stats>
                <stat n="100" nulls="0"/>
                <enum code="1" count="55">Male</enum>
                <enum code="2" count="45">Female</enum>
              </stats></total>
            </variable>
        """)
        dist = ed.extract_distribution(var, "SEX", "phv001.v1.p1", "pht001.v1", "Table")
        assert dist is not None
        assert dist.n == 100
        assert dist.nulls == 0
        assert len(dist.categories) == 2
        assert dist.categories[0]["label"] == "Male"
        assert dist.categories[0]["count"] == 55

    def test_returns_none_without_stats(self):
        var = self._make_variable("""
            <variable id="phv001.v1.p1" var_name="SEX">
              <description>No stats here</description>
            </variable>
        """)
        assert ed.extract_distribution(var, "SEX", "phv001.v1.p1", "d", "t") is None

    def test_returns_none_without_stat_element(self):
        var = self._make_variable("""
            <variable id="phv001.v1.p1" var_name="SEX">
              <total><stats></stats></total>
            </variable>
        """)
        assert ed.extract_distribution(var, "SEX", "phv001.v1.p1", "d", "t") is None

    def test_returns_none_without_enums(self):
        var = self._make_variable("""
            <variable id="phv001.v1.p1" var_name="SEX">
              <total><stats>
                <stat n="75" nulls="0" mean="1.4" min="1" max="2"/>
              </stats></total>
            </variable>
        """)
        assert ed.extract_distribution(var, "SEX", "phv001.v1.p1", "d", "t") is None

    def test_categories_sorted_descending(self):
        var = self._make_variable("""
            <variable id="phv001.v1.p1" var_name="RACE">
              <total><stats>
                <stat n="100" nulls="0"/>
                <enum code="1" count="10">Asian</enum>
                <enum code="2" count="60">White</enum>
                <enum code="3" count="30">Black</enum>
              </stats></total>
            </variable>
        """)
        dist = ed.extract_distribution(var, "RACE", "phv001.v1.p1", "d", "t")
        counts = [c["count"] for c in dist.categories]
        assert counts == [60, 30, 10]

    def test_null_code_attribute(self):
        """String-type enums may lack a code attribute."""
        var = self._make_variable("""
            <variable id="phv001.v1.p1" var_name="RACE">
              <total><stats>
                <stat n="50" nulls="0"/>
                <enum count="30">WHITE</enum>
                <enum count="20">BLACK</enum>
              </stats></total>
            </variable>
        """)
        dist = ed.extract_distribution(var, "RACE", "phv001.v1.p1", "d", "t")
        assert dist.categories[0]["code"] is None
        assert dist.categories[0]["label"] == "WHITE"


# ===========================================================================
# Integration tests: filesystem + XML parsing
# ===========================================================================


class TestFindSubjectPhenotypes:
    def test_finds_matching_file(self, study_tree):
        path = ed.find_subject_phenotypes("phs000001")
        assert path is not None
        assert "Subject_Phenotypes" in path.name
        assert path.name.startswith("phs000001.")

    def test_returns_none_for_missing_directory(self, study_tree):
        assert ed.find_subject_phenotypes("phs999999") is None

    def test_returns_none_when_no_subject_phenotypes(self, study_tree):
        assert ed.find_subject_phenotypes("phs000099") is None

    def test_does_not_match_substudy_files(self, study_tree):
        study_dir = ed.DBGAP_VARIABLES_DIR / "phs000001"
        (study_dir / "phs000999.v1.pht009999.v1.p1.Other_Subject_Phenotypes.var_report.xml").write_text(
            "<data_table/>"
        )
        path = ed.find_subject_phenotypes("phs000001")
        assert path.name.startswith("phs000001.")


class TestParseSubjectPhenotypes:
    def test_extracts_sex_and_race(self, study_tree):
        path = ed.find_subject_phenotypes("phs000001")
        study_name, sex_dists, race_dists = ed.parse_subject_phenotypes(path)

        assert study_name == "Test Study Alpha"
        assert len(sex_dists) == 1
        assert len(race_dists) == 1

    def test_skips_consent_variants(self, study_tree):
        path = ed.find_subject_phenotypes("phs000001")
        _, sex_dists, _ = ed.parse_subject_phenotypes(path)

        assert len(sex_dists) == 1
        assert sex_dists[0].n == 100  # not the .c1 variant (n=80)

    def test_skips_non_demographic_variables(self, study_tree):
        path = ed.find_subject_phenotypes("phs000001")
        _, sex_dists, race_dists = ed.parse_subject_phenotypes(path)

        all_names = [d.name for d in sex_dists + race_dists]
        assert "AGE" not in all_names
        assert "SUBJID" not in all_names

    def test_no_demographics_returns_empty(self, study_tree):
        path = ed.find_subject_phenotypes("phs000003")
        _, sex_dists, race_dists = ed.parse_subject_phenotypes(path)
        assert sex_dists == []
        assert race_dists == []

    def test_no_enums_returns_empty(self, study_tree):
        path = ed.find_subject_phenotypes("phs000004")
        _, sex_dists, _ = ed.parse_subject_phenotypes(path)
        assert sex_dists == []

    def test_best_variable_selected_from_multiple(self, study_tree):
        path = ed.find_subject_phenotypes("phs000002")
        _, sex_dists, _ = ed.parse_subject_phenotypes(path)

        best = ed.select_best_variable(sex_dists)
        assert best.n == 200
        assert best.name == "Sex"


class TestLoadComputedAncestry:
    def test_parses_csv(self, study_tree):
        ancestry, study_names = ed.load_computed_ancestry()

        assert "phs000001" in ancestry
        cats = ancestry["phs000001"]
        assert cats[0] == {"count": 60, "label": "European"}
        assert cats[1] == {"count": 30, "label": "African American"}
        assert cats[2] == {"count": 10, "label": "East Asian"}

    def test_ancestry_only_study(self, study_tree):
        ancestry, _ = ed.load_computed_ancestry()
        assert "phs000005" in ancestry
        assert ancestry["phs000005"][0] == {"count": 100, "label": "Hispanic2"}

    def test_skips_empty_ancestry(self, study_tree):
        ancestry, _ = ed.load_computed_ancestry()
        assert "phs000006" not in ancestry

    def test_returns_study_names(self, study_tree):
        _, study_names = ed.load_computed_ancestry()
        assert study_names["phs000001"] == "Test Study Alpha"
        assert study_names["phs000005"] == "Ancestry Only Study"
        assert study_names["phs000006"] == "No Ancestry Study"

    def test_missing_csv_returns_empty(self, study_tree):
        ed.DBGAP_CSV = Path("/nonexistent/file.csv")
        ancestry, study_names = ed.load_computed_ancestry()
        assert ancestry == {}
        assert study_names == {}


class TestProcessStudy:
    def test_full_result(self, study_tree):
        ancestry, csv_names = ed.load_computed_ancestry()
        result = ed.process_study("phs000001", ancestry, csv_names)

        assert result is not None
        assert result["studyName"] == "Test Study Alpha"
        assert result["sex"]["variableName"] == "SEX"
        assert result["sex"]["n"] == 100
        assert result["raceEthnicity"]["variableName"] == "RACE"
        assert result["computedAncestry"]["n"] == 100

    def test_ancestry_only_has_study_name(self, study_tree):
        """Ancestry-only studies should get their name from the CSV."""
        ancestry, csv_names = ed.load_computed_ancestry()
        result = ed.process_study("phs000005", ancestry, csv_names)

        assert result is not None
        assert result["studyName"] == "Ancestry Only Study"
        assert "sex" not in result
        assert "raceEthnicity" not in result
        assert result["computedAncestry"]["n"] == 150

    def test_no_data_returns_none(self, study_tree):
        ancestry, csv_names = ed.load_computed_ancestry()
        assert ed.process_study("phs000003", ancestry, csv_names) is None

    def test_missing_study_returns_none(self, study_tree):
        assert ed.process_study("phs999999") is None
