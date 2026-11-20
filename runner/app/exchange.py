"""Writes job output to the exchange volume (AD-19).

Layout for one inspection job:

    out/{job_id}/screenshot.png        full-page screenshot (if one could be taken)
    out/{job_id}/crops/{finding_id}.png
    out/{job_id}/result.json           contracts.InspectionResult
    out/{job_id}/error.json            contracts.ErrorEnvelope, only if the job crashed
    out/{job_id}/DONE                  written last; the backend imports only after it exists
"""

import os
import re
from pathlib import Path

from pydantic import BaseModel

SAFE_JOB_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def job_dir(exchange_dir: Path, job_id: str) -> Path:
    """out/{job_id}/ with the id checked, so a job id can never escape the volume."""
    if not SAFE_JOB_ID.match(job_id):
        raise ValueError(f"unsafe job_id: {job_id!r}")
    return exchange_dir / "out" / job_id


def write_json(path: Path, model: BaseModel) -> None:
    """Write atomically: a reader never sees half a file."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(model.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, path)


def write_done(directory: Path) -> None:
    (directory / "DONE").write_text("", encoding="utf-8")
