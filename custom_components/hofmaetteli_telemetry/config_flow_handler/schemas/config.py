"""Config flow schemas for the user, reconfigure, reauth and entity selection steps."""

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import probatio

from custom_components.hofmaetteli_telemetry.const import CONF_ENTITIES
from homeassistant.const import CONF_API_TOKEN, CONF_URL, CONF_VERIFY_SSL
from homeassistant.helpers import selector

if TYPE_CHECKING:
    from collections.abc import Iterable

    from custom_components.hofmaetteli_telemetry.api import RemoteEntity

_URL_SELECTOR = selector.TextSelector(
    selector.TextSelectorConfig(type=selector.TextSelectorType.URL),
)
_TOKEN_SELECTOR = selector.TextSelector(
    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD),
)


def get_connection_schema(defaults: Mapping[str, Any] | None = None) -> probatio.Schema:
    """
    Build the schema for the user and reconfigure steps.

    Args:
        defaults: Previously submitted or stored values, used to pre-fill the form. The token is never pre-filled.

    Returns:
        The probatio schema for the connection form.

    """
    defaults = defaults or {}
    return probatio.Schema(
        {
            probatio.Required(
                CONF_URL,
                default=defaults.get(CONF_URL, probatio.UNDEFINED),
            ): _URL_SELECTOR,
            probatio.Required(CONF_API_TOKEN): _TOKEN_SELECTOR,
            probatio.Optional(
                CONF_VERIFY_SSL,
                default=defaults.get(CONF_VERIFY_SSL, True),
            ): selector.BooleanSelector(),
        },
    )


def get_token_schema() -> probatio.Schema:
    """
    Build the schema for the reauth step, which only replaces the token.

    Returns:
        The probatio schema for the token form.

    """
    return probatio.Schema({probatio.Required(CONF_API_TOKEN): _TOKEN_SELECTOR})


def get_entities_schema(
    remote_entities: Iterable[RemoteEntity],
    selected: Iterable[str] = (),
) -> probatio.Schema:
    """
    Build the multi-select of remote entities to mirror.

    Selected entities the server no longer reports stay in the list, so the user can see and deselect them.

    Args:
        remote_entities: The entities the server currently reports.
        selected: The remote entity IDs selected so far.

    Returns:
        The probatio schema for the entity selection form.

    """
    selected = list(selected)
    labels = {entity.entity_id: f"{entity.friendly_name} ({entity.entity_id})" for entity in remote_entities}
    for entity_id in selected:
        labels.setdefault(entity_id, entity_id)

    options = [
        selector.SelectOptionDict(value=entity_id, label=label)
        for entity_id, label in sorted(labels.items(), key=lambda item: item[1].casefold())
    ]
    return probatio.Schema(
        {
            probatio.Required(CONF_ENTITIES, default=selected): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                ),
            ),
        },
    )


def get_local_entities_schema(selected: Iterable[str] = ()) -> probatio.Schema:
    """
    Build the picker for the local entities to share.

    Args:
        selected: The entity IDs selected so far.

    Returns:
        The probatio schema for the share selection form.

    """
    return probatio.Schema(
        {
            probatio.Required(CONF_ENTITIES, default=list(selected)): selector.EntitySelector(
                selector.EntitySelectorConfig(multiple=True),
            ),
        },
    )


__all__ = [
    "get_connection_schema",
    "get_entities_schema",
    "get_local_entities_schema",
    "get_token_schema",
]
