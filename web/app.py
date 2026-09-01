"""
Interface web pra gerar os relatórios em PDF sob demanda — substitui o
mLabs. Login simples por senha: uma senha de admin (vê as 3 marcas) e uma
senha por marca (cliente só vê a própria).

Rodar localmente:
    cd analise-campanhas
    source .venv/bin/activate
    set -a && source .env && set +a
    export ADMIN_PASSCODE=trocar-por-uma-senha
    export FLASK_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(16))")
    python3 web/app.py

Em produção (Render): gunicorn web.app:app — ver render.yaml.
"""

import glob
import os
import subprocess
import sys
from pathlib import Path

from flask import Flask, abort, redirect, render_template, request, send_file, session, url_for

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from etl.common import load_config  # noqa: E402
from etl.leads_config import NotConfigured, get_leads_sheet_url, is_configured, set_leads_sheet_url  # noqa: E402

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-troque-em-producao")

DAY_PRESETS = [7, 14, 30, 90]


def brand_passcode_env(brand_key: str) -> str:
    return f"PASSCODE_{brand_key.upper()}"


def get_brands() -> dict:
    return load_config()["brands"]


def current_role():
    """Retorna ('admin', None) ou ('cliente', brand_key) ou (None, None)."""
    if session.get("role") == "admin":
        return "admin", None
    if session.get("role") == "cliente" and session.get("brand_key"):
        return "cliente", session["brand_key"]
    return None, None


def require_login():
    role, _ = current_role()
    if role is None:
        return redirect(url_for("login"))
    return None


@app.route("/", methods=["GET"])
def index():
    role, brand_key = current_role()
    if role is None:
        return redirect(url_for("login"))
    if role == "cliente":
        return redirect(url_for("dashboard", brand=brand_key))
    return redirect(url_for("dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        senha = request.form.get("senha", "")
        admin_passcode = os.environ.get("ADMIN_PASSCODE")
        if admin_passcode and senha == admin_passcode:
            session.clear()
            session["role"] = "admin"
            return redirect(url_for("dashboard"))

        # tenta achar uma marca cuja senha bata
        matched = None
        for brand_key in get_brands():
            expected = os.environ.get(brand_passcode_env(brand_key))
            if expected and senha == expected:
                matched = brand_key
                break
        if matched:
            session.clear()
            session["role"] = "cliente"
            session["brand_key"] = matched
            return redirect(url_for("dashboard", brand=matched))

        error = "Senha incorreta."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
def dashboard():
    redirect_resp = require_login()
    if redirect_resp:
        return redirect_resp
    role, own_brand_key = current_role()
    brands = get_brands()

    selected_brand = request.args.get("brand") or own_brand_key
    if role == "cliente" and selected_brand != own_brand_key:
        abort(403)
    if selected_brand and selected_brand not in brands:
        abort(404)

    return render_template(
        "dashboard.html",
        role=role,
        brands=brands,
        selected_brand=selected_brand,
        selected_brand_name=brands[selected_brand]["display_name"] if selected_brand else None,
        day_presets=DAY_PRESETS,
    )


@app.route("/configuracoes", methods=["GET", "POST"])
def configuracoes():
    redirect_resp = require_login()
    if redirect_resp:
        return redirect_resp
    role, _ = current_role()
    if role != "admin":
        abort(403)

    brands = get_brands()
    saved = False
    config_error = None if is_configured() else (
        "Credenciais do Google Sheets não configuradas no ambiente deste servidor "
        "(GOOGLE_SHEETS_REFRESH_TOKEN / GOOGLE_SHEETS_SPREADSHEET_ID) — o link não pode "
        "ser salvo até isso ser adicionado no Render."
    )

    if request.method == "POST":
        brand_key = request.form.get("brand")
        url = request.form.get("leads_sheet_url", "").strip()
        if brand_key in brands and url and config_error is None:
            try:
                set_leads_sheet_url(brand_key, url)
                saved = True
            except NotConfigured as ex:
                config_error = str(ex)
        selected_brand = brand_key
    else:
        selected_brand = request.args.get("brand") or next(iter(brands))

    current_url = get_leads_sheet_url(selected_brand) if selected_brand in brands else None

    return render_template(
        "configuracoes.html",
        brands=brands,
        selected_brand=selected_brand,
        current_url=current_url,
        saved=saved,
        config_error=config_error,
    )


@app.route("/gerar", methods=["POST"])
def gerar():
    redirect_resp = require_login()
    if redirect_resp:
        return redirect_resp
    role, own_brand_key = current_role()

    brand_key = request.form.get("brand")
    if role == "cliente" and brand_key != own_brand_key:
        abort(403)
    brands = get_brands()
    if brand_key not in brands:
        abort(404)

    try:
        days = int(request.form.get("days", 30))
    except ValueError:
        days = 30
    days = max(1, min(days, 90))

    env = os.environ.copy()
    result = subprocess.run(
        [sys.executable, "etl/run_pipeline.py", "--brand", brand_key, "--days", str(days)],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )

    pdf_path = None
    for line in result.stdout.splitlines():
        if line.startswith("PDF_PATH:"):
            pdf_path = line.split("PDF_PATH:", 1)[1].strip()

    if result.returncode != 0 or not pdf_path or not os.path.exists(pdf_path):
        return render_template(
            "erro.html",
            log=(result.stdout + "\n" + result.stderr)[-4000:],
        ), 500

    filename = f"relatorio-{brand_key}-{days}dias.pdf"
    return send_file(pdf_path, as_attachment=True, download_name=filename, mimetype="application/pdf")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
