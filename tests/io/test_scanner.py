import pytest

from ephys_analysis.io import scanner
from ephys_analysis.io.scanner import scan_project_folder, parse_abf_filename


class _FakeAbf:
    """Stand-in for a loaded ABF — only needs a .protocol attribute."""
    def __init__(self, protocol: str):
        self.protocol = protocol


class TestScanProjectFolder:
    def test_discovers_every_sample_directory(self, sample_data_root):
        """Scanner finds every <animal>/<sample>/ directory containing ABFs."""
        expected = {
            (animal_dir.name, sample_dir.name)
            for animal_dir in sample_data_root.iterdir() if animal_dir.is_dir()
            for sample_dir in animal_dir.iterdir()
            if sample_dir.is_dir() and any(sample_dir.glob("*.abf"))
        }

        result = scan_project_folder(sample_data_root)

        assert set(result.samples.keys()) == expected

    def test_sample_1666_has_all_11_protocols(self, sample_data_root):
        result = scan_project_folder(sample_data_root)

        info = next(
            info for (_, sid), info in result.samples.items() if sid == "1666"
        )
        expected = {
            "1. Spontaneous EPSCs",
            "2. Resting Membrane Potential",
            "3. Membrane Test",
            "4. Ih and Input Resistance",
            "5a. Single AP coarse",
            "5b. Single AP fine",
            "6. Ramp 6s",
            "7. 5 Spike AHP",
            "8. 25 Spike AHP",
            "9. 1s AP Firing",
            "11. 50 Spike AHP",
        }
        assert set(info.protocols.keys()) == expected

    def test_extracts_collection_date_from_filename(self, sample_data_root):
        result = scan_project_folder(sample_data_root)

        info = next(
            info for (_, sid), info in result.samples.items() if sid == "1666"
        )
        assert info.collection_date == "2026_02_04"

    def test_extracts_experimenter_from_filename(self, sample_data_root):
        result = scan_project_folder(sample_data_root)

        info = next(
            info for (_, sid), info in result.samples.items() if sid == "1666"
        )
        assert info.experimenter == "JCA"


class TestScanProjectFolderDuplicates:
    """Positive-path coverage for duplicate detection.

    Uses a synthetic project tree and monkeypatches the ABF reader so the
    scanner sees whatever protocol name we assign per file. This isolates
    the grouping logic from real ABF parsing.
    """

    @pytest.fixture
    def project_with_dupes(self, tmp_path, monkeypatch):
        animal = tmp_path / "animalA"
        sample = animal / "1666"
        sample.mkdir(parents=True)
        path_a = sample / "2026_01_01_JCA_0001.abf"
        path_b = sample / "2026_01_01_JCA_0002.abf"
        path_c = sample / "2026_01_01_JCA_0003.abf"
        for p in (path_a, path_b, path_c):
            p.write_bytes(b"")

        # path_a/path_b share a protocol → duplicate; path_c is unique.
        protocols_by_name = {
            path_a.name: "DUP_PROTOCOL",
            path_b.name: "DUP_PROTOCOL",
            path_c.name: "UNIQUE_PROTOCOL",
        }
        monkeypatch.setattr(
            scanner, "load_abf",
            lambda path, load_data=False: _FakeAbf(protocols_by_name[path.name]),
        )
        monkeypatch.setattr(
            scanner, "get_protocol_name",
            lambda abf: abf.protocol,
        )
        return tmp_path, path_a, path_b, path_c

    def test_duplicate_protocol_files_are_recorded(self, project_with_dupes):
        root, path_a, path_b, _ = project_with_dupes

        result = scan_project_folder(root)

        key = ("animalA", "1666", "DUP_PROTOCOL")
        assert sorted(result.duplicates[key]) == sorted([path_a, path_b])

    def test_surviving_protocol_entry_is_first_path(self, project_with_dupes):
        root, path_a, _, _ = project_with_dupes

        result = scan_project_folder(root)
        info = result.samples[("animalA", "1666")]

        assert info.protocols["DUP_PROTOCOL"] == path_a

    def test_unique_protocols_not_marked_as_duplicates(self, project_with_dupes):
        root, _, _, _ = project_with_dupes

        result = scan_project_folder(root)

        assert ("animalA", "1666", "UNIQUE_PROTOCOL") not in result.duplicates

    def test_unique_protocol_still_in_sample_protocols(self, project_with_dupes):
        root, _, _, path_c = project_with_dupes

        result = scan_project_folder(root)
        info = result.samples[("animalA", "1666")]

        assert info.protocols["UNIQUE_PROTOCOL"] == path_c

    def test_only_one_duplicate_group_for_two_dupes(self, project_with_dupes):
        root, _, _, _ = project_with_dupes

        result = scan_project_folder(root)

        assert len(result.duplicates) == 1


class TestParseAbfFilename:
    def test_standard_filename(self):
        assert parse_abf_filename("2026_02_04_JCA_0000") == ("2026_02_04", "JCA")

    def test_different_initials(self):
        assert parse_abf_filename("2026_02_04_DMG_0005") == ("2026_02_04", "DMG")

    def test_date_only_filename_returns_date_and_empty_initials(self):
        assert parse_abf_filename("2025_12_10_0000") == ("2025_12_10", "")

    def test_animal_prefixed_filename_returns_empty(self):
        assert parse_abf_filename("63550_0011") == ("", "")

    def test_invalid_filename_returns_empty(self):
        assert parse_abf_filename("bad_name") == ("", "")


class TestScannerDateExperimenterRecovery:
    """Real ABF data: scanner must populate Date for every sample regardless
    of filename convention. Experimenter is filename-only — present for the
    `_JCA_`-style names, blank for the older `<animal>_NNNN` and
    date-only naming conventions.
    """

    def test_date_from_filename_with_initials(self, sample_data_root):
        """Sample 1666 uses YYYY_MM_DD_INITIALS_NNNN — date comes from filename."""
        result = scan_project_folder(sample_data_root)
        info = next(i for (_, sid), i in result.samples.items() if sid == "1666")
        assert info.collection_date == "2026_02_04"

    def test_date_from_filename_without_initials(self, sample_data_root):
        """Sample 1542 uses YYYY_MM_DD_NNNN — date still recovered from filename."""
        result = scan_project_folder(sample_data_root)
        info = next(i for (_, sid), i in result.samples.items() if sid == "1542")
        assert info.collection_date == "2025_12_10"

    def test_date_from_abf_header_when_filename_has_none(self, sample_data_root):
        """Sample 1533 uses <animal>_NNNN — date falls back to ABF header."""
        result = scan_project_folder(sample_data_root)
        info = next(i for (_, sid), i in result.samples.items() if sid == "1533")
        # 63550_0010.abf's header records 2025-11-24.
        assert info.collection_date == "2025_11_24"

    def test_no_sample_has_blank_date(self, sample_data_root):
        """After the filename loosening + ABF-header fallback, every sample
        must have a non-empty collection_date.
        """
        result = scan_project_folder(sample_data_root)
        blank = [
            (info.animal_id, info.sample_id) for info in result.samples.values()
            if not info.collection_date
        ]
        assert blank == [], f"Samples missing date: {blank}"
