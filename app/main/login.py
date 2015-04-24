from . import main
from flask import render_template, redirect, url_for


@main.route('/login', methods=["GET"])
def render_login():
    template_data = main.config['BASE_TEMPLATE_DATA']
    return render_template("auth/login.html", **template_data), 200


@main.route('/login', methods=["POST"])
def process_login():
    return redirect(url_for('.dashboard'))


@main.route('/logout', methods=["GET"])
def logout():
    return redirect(url_for('.render_login'))


@main.route('/forgotten-password', methods=["GET"])
def forgotten_password():
    template_data = main.config['BASE_TEMPLATE_DATA']

    return render_template("auth/forgotten-password.html",
                           **template_data), 200


@main.route('/forgotten-password', methods=["POST"])
def send_reset_email():
    return redirect(url_for('.change_password'))


@main.route('/change-password', methods=["GET"])
def change_password():
    template_data = main.config['BASE_TEMPLATE_DATA']

    return render_template("auth/change-password.html", **template_data), 200


@main.route('/change-password', methods=["POST"])
def update_password():
    return redirect(url_for('.password_changed'))


@main.route('/password-changed', methods=["GET"])
def password_changed():
    template_data = main.config['BASE_TEMPLATE_DATA']

    return render_template("auth/password-changed.html", **template_data), 200