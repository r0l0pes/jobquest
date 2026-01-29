#!/usr/bin/env python3
"""Compile a .tex file to PDF using pdflatex. Outputs JSON result to stdout, status to stderr."""

import sys
import os
import json
import subprocess


def compile_tex(tex_path):
    """Run pdflatex twice on the given .tex file and return the PDF path."""
    tex_path = os.path.abspath(tex_path)
    if not os.path.exists(tex_path):
        return {"success": False, "error": f"File not found: {tex_path}"}

    output_dir = os.path.dirname(tex_path)
    basename = os.path.splitext(os.path.basename(tex_path))[0]
    pdf_path = os.path.join(output_dir, f"{basename}.pdf")

    cmd = [
        "pdflatex",
        "-interaction=nonstopmode",
        f"-output-directory={output_dir}",
        tex_path,
    ]

    # Run twice for cross-references
    for run in (1, 2):
        print(f"pdflatex pass {run}...", file=sys.stderr)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            # Extract relevant error lines from pdflatex output
            error_lines = []
            for line in result.stdout.split("\n"):
                if line.startswith("!") or "Error" in line or "Fatal" in line:
                    error_lines.append(line)
            return {
                "success": False,
                "error": "pdflatex failed",
                "details": error_lines[:10],
                "returncode": result.returncode,
            }

    if not os.path.exists(pdf_path):
        return {"success": False, "error": f"PDF not generated at {pdf_path}"}

    print(f"PDF generated: {pdf_path}", file=sys.stderr)
    return {"success": True, "pdf_path": pdf_path, "tex_path": tex_path}


def main():
    if len(sys.argv) < 2:
        print("Usage: render_pdf.py <path_to_tex_file>", file=sys.stderr)
        sys.exit(1)

    tex_path = sys.argv[1]
    result = compile_tex(tex_path)
    print(json.dumps(result, indent=2))

    if not result["success"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
