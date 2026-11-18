import pytest
from fastapi import HTTPException

from mysite.services.text_checks import (
    check_form_texts,
    validate_class_letter,
    validate_free_text,
    validate_person_name,
    validate_subject_name,
)

GOOD_SUBJECTS = ["Кыргыз тили", "Кыргызский язык", "Математика", "Дүйнөлүк тарых", "Шахматы"]
BAD_SUBJECTS = ["хуй", "xуйня", "Physics", "Математика 5-класс", "Мат", "", "<script>"]
GOOD_PEOPLE = ["Асанов Бакыт", "Алиева Назира", "Мамытов Эркин уулу", "Өмүрбекова Айгүл", "O'Neil John", "Анна-Мария Петрова"]
BAD_PEOPLE = ["Сука Тупая", "хуй", "Ivan123", "Асанов!!!", "ааааа", "Иван_Петров", "x"]


@pytest.mark.parametrize("name", GOOD_SUBJECTS)
def test_good_subject_names_pass(name):
    assert validate_subject_name(f"  {name} ") == name


@pytest.mark.parametrize("name", BAD_SUBJECTS)
def test_bad_subject_names_fail(name):
    with pytest.raises(ValueError):
        validate_subject_name(name)


@pytest.mark.parametrize("name", GOOD_PEOPLE)
def test_good_person_names_pass(name):
    assert validate_person_name(f" {name}  ") == name


@pytest.mark.parametrize("name", BAD_PEOPLE)
def test_bad_person_names_fail(name):
    with pytest.raises(ValueError):
        validate_person_name(name)


def test_person_name_collapses_spaces():
    assert validate_person_name("Асанов   Бакыт") == "Асанов Бакыт"


@pytest.mark.parametrize("letter", ["А", "Б", "Ө", "AB"])
def test_good_class_letters(letter):
    assert validate_class_letter(letter) == letter


@pytest.mark.parametrize("letter", ["1", "А-1", "ХУЙ", "!", "ABCD"])
def test_bad_class_letters(letter):
    with pytest.raises(ValueError):
        validate_class_letter(letter)


def test_free_text_allows_normal_text():
    text = "Завтра в 9:00 собрание родителей. Тема: учебник по математике, небо и страны мира!"
    assert validate_free_text(text) == text
    assert validate_free_text(None) is None


@pytest.mark.parametrize("text", ["Ты сука", "это полная хуйня", "fuck this", "ну и жопа"])
def test_free_text_blocks_profanity(text):
    with pytest.raises(ValueError):
        validate_free_text(text)


def test_check_form_texts_returns_field_errors():
    check_form_texts(title="Собрание", body=None)
    with pytest.raises(HTTPException) as error:
        check_form_texts(title="Собрание", body="полная хуйня")
    assert error.value.status_code == 422
    assert error.value.detail[0]["loc"] == ["body", "body"]
