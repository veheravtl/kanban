from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import tempfile


class ConversionError(RuntimeError):
    """Raised when conversion into PDF fails."""


SUPPORTED_EXTENSIONS = {".doc", ".docx", ".xls", ".xlsx", ".xlsm"}

SOFFICE_STARTUP_FLAGS = [
    "--headless",
    "--nologo",
    "--nodefault",
    "--nolockcheck",
    "--norestore",
    "--invisible",
]


class ConverterAdapter:
    def __init__(
        self,
        converter_script_path: Path,
        python_bin: str = "python3",
        libreoffice_bin: str | None = None,
        timeout_sec: int = 300,
    ):
        self.converter_script_path = converter_script_path
        self.python_bin = python_bin
        self.libreoffice_bin = libreoffice_bin
        self.timeout_sec = timeout_sec

    def convert_to_pdf(self, source_file: Path, out_dir: Path) -> Path:
        extension = source_file.suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            raise ConversionError(f"Unsupported extension: {extension}")

        out_dir.mkdir(parents=True, exist_ok=True)

        if extension == ".doc":
            return self._convert_doc_with_libreoffice(source_file, out_dir)

        return self._convert_with_existing_script(source_file, out_dir)

    def _convert_with_existing_script(self, source_file: Path, out_dir: Path) -> Path:
        if not self.converter_script_path.exists():
            raise ConversionError(
                f"Converter script does not exist: {self.converter_script_path}"
            )

        cmd = [
            self.python_bin,
            str(self.converter_script_path),
            str(source_file),
            "-o",
            str(out_dir),
        ]

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=self.timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ConversionError(f"Converter timeout: {exc}") from exc
        except OSError as exc:
            raise ConversionError(f"Converter execution failed: {exc}") from exc

        if result.returncode != 0:
            details = (result.stderr.strip() or result.stdout.strip() or "unknown error")
            raise ConversionError(f"Converter script failed: {details}")

        expected_pdf = out_dir / f"{source_file.stem}.pdf"
        if expected_pdf.exists():
            return expected_pdf

        for line in reversed(result.stdout.splitlines()):
            candidate = Path(line.strip())
            if candidate.exists() and candidate.suffix.lower() == ".pdf":
                return candidate

        raise ConversionError(
            f"Converter script succeeded but PDF not found for {source_file.name}"
        )

    def _convert_doc_with_libreoffice(self, source_file: Path, out_dir: Path) -> Path:
        soffice_bin = self._find_soffice()

        with tempfile.TemporaryDirectory(prefix="soffice_profile_") as profile_dir:
            profile_uri = Path(profile_dir).resolve().as_uri()
            cmd = [
                soffice_bin,
                *SOFFICE_STARTUP_FLAGS,
                f"-env:UserInstallation={profile_uri}",
                "--convert-to",
                "pdf",
                "--outdir",
                str(out_dir),
                str(source_file),
            ]

            env = os.environ.copy()
            env.setdefault("SAL_USE_VCLPLUGIN", "svp")

            try:
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=self.timeout_sec,
                    check=False,
                    env=env,
                )
            except subprocess.TimeoutExpired as exc:
                raise ConversionError(f"LibreOffice timeout: {exc}") from exc
            except OSError as exc:
                raise ConversionError(f"LibreOffice execution failed: {exc}") from exc

        output_pdf = out_dir / f"{source_file.stem}.pdf"
        if result.returncode != 0:
            details = result.stderr.strip() or result.stdout.strip() or "unknown error"
            raise ConversionError(f"LibreOffice conversion failed: {details}")

        if not output_pdf.exists():
            details = result.stderr.strip() or result.stdout.strip() or "output pdf was not created"
            raise ConversionError(f"LibreOffice conversion failed: {details}")

        return output_pdf

    def _find_soffice(self) -> str:
        if self.libreoffice_bin:
            return self.libreoffice_bin

        for name in ("soffice", "libreoffice"):
            candidate = shutil.which(name)
            if candidate:
                return candidate

        raise ConversionError("LibreOffice is not installed or not available in PATH")
