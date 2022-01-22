import unrealsdk
from typing import Optional, Tuple

from Mods.ModMenu import Game  # type: ignore

from . import YAML, float_error
from .data import (ALLOWED_DEFINITION_CLASSES, DEFINITION_PART_TYPE, ITEM_PART_TYPE_NAMES,
                   MODIFIER_NAMES, PART_NAMES, PART_TYPE_OVERRIDES, SCALING_ATTRIBUTES,
                   SCALING_INITALIZATIONS, WEAPON_MANU_ATTRIBUTES, WEAPON_PART_TYPE_NAMES)

VALID_MANU_RESTRICT_PREPENDS: Tuple[str, ...] = (
    "Zoom",
)


def _create_bonus_data(
    part: unrealsdk.UObject,
    attr_struct: unrealsdk.FStruct,
    restrict: Optional[str] = None
) -> Optional[YAML]:
    """
    Create bonus yaml from an attribute struct.

    Args:
        part: The part currently being parsed.
        attr_struct: The attribute struct to parse.
        restrict: The base restriction to use. May be None.
    Returns:
        None if the bonus was unparseable and should be skipped.
        The bonus yaml otherwise.
    """
    bonus_data = {
        "attribute": part.PathName(attr_struct.AttributeToModify),
        "type": MODIFIER_NAMES[attr_struct.ModifierType],
    }

    bvc = attr_struct.BaseModifierValue.BaseValueConstant
    attr = attr_struct.BaseModifierValue.BaseValueAttribute
    init = attr_struct.BaseModifierValue.InitializationDefinition
    bvsc = attr_struct.BaseModifierValue.BaseValueScaleConstant

    if attr in WEAPON_MANU_ATTRIBUTES and init is None:
        value = float_error(bvsc)
        if restrict is not None and restrict not in VALID_MANU_RESTRICT_PREPENDS:
            unrealsdk.Log(
                f"Found manufacturer restriction on bonus with existing restriction"
                f" {part.PathName(part)}"
            )
        manu_restrict = WEAPON_MANU_ATTRIBUTES[attr]
        if restrict in VALID_MANU_RESTRICT_PREPENDS:
            restrict = manu_restrict + " + " + restrict
        else:
            restrict = manu_restrict
    elif attr in SCALING_ATTRIBUTES and init is None:
        scale, scale_multi = SCALING_ATTRIBUTES[attr]
        value = float_error(scale_multi * bvsc)
        bonus_data["scale"] = scale
    elif attr is None and init in SCALING_INITALIZATIONS:
        scale, scale_multi = SCALING_INITALIZATIONS[init]
        value = float_error(scale_multi * bvsc)
        bonus_data["scale"] = scale
    elif attr is not None or init is not None:
        unrealsdk.Log(f"Unparsable bonus on {part.PathName(part)}")
        return None
    else:
        value = float_error(bvc * bvsc)

    if value == 0:
        return None

    bonus_data["value"] = value
    if restrict is not None:
        bonus_data["restrict"] = restrict

    return bonus_data


def get_part_data(part: unrealsdk.UObject) -> Tuple[str, YAML]:
    """
    Gets data about the provided part.

    Args:
        part: The part object to process
    Returns:
        A tuple of the part's type, and the YAML data describing it
    """
    part_name = part.PathName(part)

    part_type_names = (
        WEAPON_PART_TYPE_NAMES
        if part.Class.Name == "WeaponPartDefinition" else
        ITEM_PART_TYPE_NAMES
    )

    part_type: str
    if part_name in PART_TYPE_OVERRIDES:
        part_type = PART_TYPE_OVERRIDES[part_name]
    elif part.Class.Name in ALLOWED_DEFINITION_CLASSES:
        part_type = DEFINITION_PART_TYPE
    elif part.Material is not None:
        part_type = part_type_names[8]
    elif 0 <= part.PartType < len(part_type_names):
        part_type = part_type_names[part.PartType]
    else:
        raise ValueError(f"Bad part type {part.PartType} on {part_name}")

    all_bonuses = []

    for grade in part.AttributeSlotUpgrades:
        if grade.GradeIncrease == 0:
            continue
        all_bonuses.append({
            "slot": grade.SlotName,
            "value": grade.GradeIncrease,
            "type": "grade",
        })

    for attr_group, base_restrict in (
        (part.WeaponAttributeEffects, None),
        (part.ItemAttributeEffects, None),
        (part.ExternalAttributeEffects, None),
        (part.ZoomWeaponAttributeEffects, "Zoom"),
        (part.ZoomExternalAttributeEffects, "Zoom"),
    ):
        if attr_group is None:
            continue
        for attr_struct in attr_group:
            bonus_data = _create_bonus_data(part, attr_struct, base_restrict)
            if bonus_data is not None:
                all_bonuses.append(bonus_data)

    # This catches the fibber, we'll see if it works for anything else
    if part.BehaviorProviderDefinition is not None:
        for seq in part.BehaviorProviderDefinition.BehaviorSequences:
            for behaviour_struct in seq.BehaviorData2:
                if behaviour_struct.Behavior.Class.Name != "Behavior_AttributeEffect":
                    continue
                for attr_struct in behaviour_struct.Behavior.AttributeEffects:
                    bonus_data = _create_bonus_data(part, attr_struct, "Post-Init")
                    if bonus_data is not None:
                        all_bonuses.append(bonus_data)

    part_data = {
        "_obj_name": part_name
    }

    if part_name in PART_NAMES:
        name_data = PART_NAMES[part_name]
        override = name_data.get("game_overrides", {}).get(Game.GetCurrent()._name_)  # type: ignore

        part_data["name"] = override if override is not None else name_data["name"]
    else:
        part_data["name"] = part_name.split(".")[-1]

    if len(all_bonuses) > 0:
        part_data["bonuses"] = all_bonuses

    if part.GestaltModeSkeletalMeshName not in (None, "", "None") and part.bIsGestaltMode:
        part_data["mesh"] = part.GestaltModeSkeletalMeshName

    return part_type, part_data