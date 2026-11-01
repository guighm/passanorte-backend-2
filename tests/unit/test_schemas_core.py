"""Unit: contract base ``ApiModel`` (spec 005, FR-002/FR-008/FR-012).

The base must generate camelCase JSON aliases from snake_case Python
attributes (full-lowercase acronym folding — Q2), forbid unknown keys and
REJECT snake_case input keys at validation time (no ``populate_by_name`` —
research R1). Internal attribute names stay snake_case (PEP 8, FR-002).
"""

import pytest
from pydantic import ValidationError

from passanorte_back.core.schemas import ApiModel


class _Sample(ApiModel):
    """Exercise schema with fold and non-fold attribute names."""

    first_name: str
    user_cpf: str
    cpf: str


def test_camelcase_aliases_are_generated_from_snake_case_attributes() -> None:
    dumped = _Sample.from_internal(first_name="Ana", user_cpf="123", cpf="456").model_dump(
        by_alias=True
    )
    assert dumped == {"firstName": "Ana", "userCpf": "123", "cpf": "456"}


def test_direct_camel_construction_still_validates() -> None:
    model = _Sample(firstName="Ana", userCpf="123", cpf="456")
    assert model.first_name == "Ana"


def test_acronyms_fold_to_full_lowercase_clar_q2() -> None:
    # 'cpf' stays as-is; 'user_cpf' folds 'Cpf' fully lowercase (no CPF caps).
    assert _Sample.model_fields["user_cpf"].alias == "userCpf"
    assert _Sample.model_fields["cpf"].alias == "cpf"


def test_camelcase_input_is_accepted() -> None:
    model = _Sample.model_validate({"firstName": "Ana", "userCpf": "123", "cpf": "456"})
    assert model.first_name == "Ana"
    assert model.user_cpf == "123"


def test_snake_case_input_key_is_rejected() -> None:
    with pytest.raises(ValidationError) as error:
        _Sample.model_validate({"first_name": "Ana", "userCpf": "123", "cpf": "456"})
    # the snake_case key must not be silently accepted (populate_by_name off)
    assert "first_name" in str(error.value)


def test_unknown_key_is_forbidden() -> None:
    with pytest.raises(ValidationError) as error:
        _Sample.model_validate(
            {"firstName": "Ana", "userCpf": "123", "cpf": "456", "middleName": "Z"}
        )
    assert "middleName" in str(error.value)


# FR-008/FR-012 module-inheritance assertion lands with the US3 migration
# (tasks T012–T019) — until then modules still subclass plain BaseModel.


def test_canary_subclass_inherits_alias_rules() -> None:
    """SC-006: a new ApiModel subclass complies without local config."""

    class _BrandNew(ApiModel):
        tourist_spot_name: str

    field_alias = _BrandNew.model_fields["tourist_spot_name"].alias
    assert field_alias == "touristSpotName"


def test_every_module_schema_subclasses_apimodel() -> None:
    """FR-012/SC-006 guard: no module schema may escape the contract base.

    Imports every submodule of every module's ``schemas`` package and asserts
    that each class DEFINED there that subclasses ``BaseModel`` also
    subclasses ``ApiModel``. Closes the request-body blind spot of the
    sweep's static leg, which only walks ``response_model`` trees.
    """
    import importlib
    import inspect
    import pkgutil

    from pydantic import BaseModel

    from passanorte_back.core import modules as core_modules
    from passanorte_back.core.schemas import ApiModel

    checked: list[str] = []
    for domain in core_modules.DOMAIN_MODULES:
        package_name = f"passanorte_back.modules.{domain}.schemas"
        try:
            package = importlib.import_module(package_name)
        except ModuleNotFoundError:
            continue  # modules without a schemas package yet (foundation stubs)
        subpackages = [
            f"{package_name}.{info.name}"
            for info in pkgutil.iter_modules(package.__path__)
            if info.ispkg
        ]
        module_names = (
            [package_name]
            + subpackages
            + [
                f"{package_name}.{info.name}"
                for info in pkgutil.iter_modules(package.__path__)
                if not info.ispkg
            ]
        )
        for module_name in module_names:
            module = importlib.import_module(module_name)
            for name, obj in vars(module).items():
                if not inspect.isclass(obj) or obj.__module__ != module_name:
                    continue
                if issubclass(obj, BaseModel):
                    assert issubclass(obj, ApiModel), (
                        f"{module_name}.{name} is a plain BaseModel —"
                        " inherit ApiModel to join the JSON contract"
                    )
                    checked.append(f"{module_name}.{name}")
    # sanity: the guard is not vacuous — it must have seen the live DTOs
    assert any("TouristCreateRequest" in item for item in checked)
    assert any("LoginRequest" in item for item in checked)
