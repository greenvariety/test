from flask import Blueprint, render_template

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def welcome():
    return render_template('main/welcome.html') 