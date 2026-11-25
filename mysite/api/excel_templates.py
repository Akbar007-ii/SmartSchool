"""Excel жүктөө үчүн даяр үлгүлөр (шаблондор).

Мамычалар импорт эндпоинттери күткөн форматка так дал келет:
    Почта | Толук аты-жөнү
"""
from io import BytesIO

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from mysite.db.models import Users
from mysite.security.permissions import require_roles

router = APIRouter(prefix="/admin/excel/templates", tags=["Excel Templates"])

HEADERS = ["Почта", "Толук аты-жөнү"]
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def build_template(sheet_title: str, example: list, filename: str) -> StreamingResponse:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_title

    sheet.append(HEADERS)
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1D4ED8")
        cell.alignment = Alignment(horizontal="center")

    sheet.append(example)

    sheet.column_dimensions["A"].width = 32
    sheet.column_dimensions["B"].width = 40
    sheet.freeze_panes = "A2"

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/students")
def students_template(
    current_user: Users = Depends(require_roles("DIRECTOR", "DEPUTY")),
):
    return build_template(
        "Окуучулар",
        ["erkin.aliev@gmail.com", "Алиев Эркин Бакытович"],
        "students_template.xlsx",
    )


@router.get("/teachers")
def teachers_template(
    current_user: Users = Depends(require_roles("DIRECTOR", "DEPUTY")),
):
    return build_template(
        "Мугалимдер",
        ["maria.ivanova@gmail.com", "Иванова Мария Петровна"],
        "teachers_template.xlsx",
    )


PROGRAM_HEADERS = ["Бөлүм", "Тема", "Саат", "Апта", "Максаттар", "Материалдар"]


@router.get("/program")
def program_template(
    current_user: Users = Depends(require_roles("DIRECTOR", "DEPUTY")),
):
    """Окуу программасынын үлгүсү: ар бир сап — бир тема."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Программа"
    sheet.append(PROGRAM_HEADERS)
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1D4ED8")
    for row in (
        ["Сандар жана туюнтмалар", "Квадраттык теңдемелер", 2, 1,
         "Квадраттык теңдемени чыгара алат", "Окуу китеби, 12–18-беттер"],
        ["Сандар жана туюнтмалар", "Виет теоремасы", 1, 2,
         "Тамырлардын касиеттерин колдонот", "https://example.com/video"],
        ["Функциялар", "Квадраттык функция жана анын графиги", 3, 3, "", ""],
    ):
        sheet.append(row)
    for column, width in zip("ABCDEF", (26, 40, 8, 8, 40, 40)):
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = "A2"

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": 'attachment; filename="program_template.xlsx"'},
    )
