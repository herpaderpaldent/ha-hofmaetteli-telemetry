"""Options flow for hofmaetteli_telemetry: change which entities are mirrored or shared."""

from typing import Any

from custom_components.hofmaetteli_telemetry.const import CONF_ENTITIES, CONF_MODE, MODE_RECEIVE, MODE_SHARE
from homeassistant import config_entries

from .schemas import get_entities_schema, get_local_entities_schema


class HofmaetteliTelemetryOptionsFlow(config_entries.OptionsFlowWithReload):
    """Let the user change the entity selection after setup; the reload applies it."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """
        Route to the selection that matches the entry's mode.

        Returns:
            The receive or share selection step.

        """
        if self.config_entry.data.get(CONF_MODE, MODE_RECEIVE) == MODE_SHARE:
            return await self.async_step_share()
        return await self.async_step_receive()

    async def async_step_receive(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """
        Show the remote entities, offering what the server reported on the last poll.

        Returns:
            The form, or the stored options.

        """
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        coordinator = self.config_entry.runtime_data.coordinator
        remote_entities = (coordinator.data or {}).values() if coordinator else ()

        return self.async_show_form(
            step_id="receive",
            data_schema=get_entities_schema(
                remote_entities,
                selected=self.config_entry.options.get(CONF_ENTITIES, []),
            ),
        )

    async def async_step_share(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """
        Show the local entity picker with the current selection.

        Returns:
            The form, or the stored options.

        """
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="share",
            data_schema=get_local_entities_schema(self.config_entry.options.get(CONF_ENTITIES, [])),
        )


__all__ = ["HofmaetteliTelemetryOptionsFlow"]
