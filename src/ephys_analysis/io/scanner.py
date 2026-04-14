import logging
import re
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, field

from ephys_analysis.core.abf_io import load_abf, get_protocol_name

logger = logging.getLogger(__name__)


@dataclass
class SampleInfo:
    """Metadata extracted from folder structure and ABF filenames."""
    animal_id: str = ""
    sample_id: str = ""
    collection_date: str = ""  # e.g. "2026_02_04"
    experimenter: str = ""  # e.g. "JCA"
    protocols: dict[str, Path] = field(default_factory=dict)


@dataclass
class ScanResult:
    """Result of scanning a data folder."""
    # (animal_id, sample_id) → SampleInfo
    samples: dict[tuple[str, str], SampleInfo] = field(default_factory=dict)
    # Duplicates: (animal_id, sample_id, protocol_name) → [Path, ...]
    duplicates: dict[tuple[str, str, str], list[Path]] = field(default_factory=dict)


# ABF filename pattern: YYYY_MM_DD_INITIALS_NNNN
_ABF_NAME_RE = re.compile(
    r"^(\d{4}_\d{2}_\d{2})_([A-Za-z]+)_(\d{4,})$"
)


def parse_abf_filename(name: str) -> tuple[str, str]:
    """Extract collection date and experimenter initials from ABF filename.

    Args:
        name: Filename stem, e.g. "2026_02_04_JCA_0000"

    Returns:
        (collection_date, experimenter) e.g. ("2026_02_04", "JCA").
        Returns ("", "") if the pattern doesn't match.
    """
    m = _ABF_NAME_RE.match(name)
    if m:
        return m.group(1), m.group(2)
    return "", ""


def scan_project_folder(project_path: Path) -> ScanResult:  # noqa: C901
    """Walk Animal ID / Sample # / *.abf and group by protocol.

    Expected structure:
        project_path / animal_id_folder / sample_folder / *.abf

    Returns a ScanResult with samples, extracted metadata, and any duplicates.
    """
    result = ScanResult()
    project_path = Path(project_path)

    try:
        animal_dirs = sorted(project_path.iterdir())
    except PermissionError:
        logger.warning("Permission denied reading %s", project_path)
        return result

    for animal_dir in animal_dirs:
        if not animal_dir.is_dir():
            continue
        animal_id = animal_dir.name

        try:
            sample_dirs = sorted(animal_dir.iterdir())
        except PermissionError:
            logger.warning("Permission denied reading %s", animal_dir)
            continue

        for sample_dir in sample_dirs:
            if not sample_dir.is_dir():
                continue
            sample_id = sample_dir.name
            key = (animal_id, sample_id)

            info = SampleInfo(animal_id=animal_id, sample_id=sample_id)

            # Group ABF files by protocol
            protocol_files: dict[str, list[Path]] = defaultdict(list)
            for abf_path in sorted(sample_dir.glob("*.abf")):
                try:
                    abf = load_abf(abf_path, load_data=False)
                    protocol = get_protocol_name(abf)
                    protocol_files[protocol].append(abf_path)

                    # Extract date/experimenter from first parseable filename
                    if not info.collection_date:
                        date, exp = parse_abf_filename(abf_path.stem)
                        if date:
                            info.collection_date = date
                            info.experimenter = exp
                except Exception as e:
                    logger.warning("Skipping %s: %s", abf_path.name, e)
                    continue

            # Separate singles from duplicates
            for protocol, paths in protocol_files.items():
                if len(paths) == 1:
                    info.protocols[protocol] = paths[0]
                else:
                    result.duplicates[(animal_id, sample_id, protocol)] = paths
                    info.protocols[protocol] = paths[0]

            result.samples[key] = info

    return result
