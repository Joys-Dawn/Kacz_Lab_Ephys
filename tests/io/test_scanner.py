from ephys_analysis.io.scanner import scan_project_folder, parse_abf_filename


class TestScanProjectFolder:
    def test_finds_four_samples(self, sample_data_root):
        result = scan_project_folder(sample_data_root)

        assert len(result.samples) == 4

    def test_all_samples_belong_to_expected_animal(self, sample_data_root):
        result = scan_project_folder(sample_data_root)

        for (animal_id, sample_id) in result.samples:
            assert animal_id == "55 - 64280"
            assert sample_id in ("1666", "1667", "1668", "1669")

    def test_sample_1666_has_all_11_protocols(self, sample_data_root):
        result = scan_project_folder(sample_data_root)
        info = result.samples[("55 - 64280", "1666")]
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

    def test_no_duplicates_in_sample_data(self, sample_data_root):
        result = scan_project_folder(sample_data_root)

        assert len(result.duplicates) == 0

    def test_extracts_collection_date_from_filename(self, sample_data_root):
        result = scan_project_folder(sample_data_root)
        info = result.samples[("55 - 64280", "1666")]

        assert info.collection_date == "2026_02_04"

    def test_extracts_experimenter_from_filename(self, sample_data_root):
        result = scan_project_folder(sample_data_root)
        info = result.samples[("55 - 64280", "1666")]

        assert info.experimenter == "JCA"


class TestParseAbfFilename:
    def test_standard_filename(self):
        assert parse_abf_filename("2026_02_04_JCA_0000") == ("2026_02_04", "JCA")

    def test_different_initials(self):
        assert parse_abf_filename("2026_02_04_DMG_0005") == ("2026_02_04", "DMG")

    def test_invalid_filename_returns_empty(self):
        assert parse_abf_filename("bad_name") == ("", "")
