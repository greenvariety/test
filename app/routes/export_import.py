from flask import Blueprint, send_file
from app import db
from app.models import Faculty, Group, Student
import pandas as pd
import io

export_import_bp = Blueprint('export_import', __name__, url_prefix='/data')

@export_import_bp.route('/export/excel')
def export_excel():
    try:
        # Извлечение данных
        faculties = Faculty.query.all()
        groups = Group.query.all()
        students = Student.query.all()

        # Преобразование в списки словарей (для Pandas DataFrame)
        faculties_data = [{'id': f.id, 'name': f.name, 'short_name': f.short_name, 'description': f.description} for f in faculties]
        groups_data = [{'id': g.id, 'name': g.name, 'year': g.year, 'duration': g.duration, 'faculty_id': g.faculty_id, 'course': g.course, 'status': g.status} for g in groups]
        students_data = [{'id': s.id, 'full_name': s.full_name, 'date_of_birth': s.date_of_birth.isoformat() if s.date_of_birth else None, 'phone_number': s.phone_number, 'email': s.email, 'group_id': s.group_id} for s in students]

        # Создание DataFrame
        df_faculties = pd.DataFrame(faculties_data)
        df_groups = pd.DataFrame(groups_data)
        df_students = pd.DataFrame(students_data)

        # Создание Excel файла в памяти
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_faculties.to_excel(writer, sheet_name='Faculties', index=False)
            df_groups.to_excel(writer, sheet_name='Groups', index=False)
            df_students.to_excel(writer, sheet_name='Students', index=False)
        
        output.seek(0)

        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='university_data_export.xlsx'
        )

    except Exception as e:
        # Можно добавить логирование ошибки здесь
        # flash(f"Ошибка при экспорте данных: {str(e)}", "danger")
        # return redirect(url_for('main.welcome')) # или куда-то еще
        return str(e), 500 # Простой ответ об ошибке для отладки 