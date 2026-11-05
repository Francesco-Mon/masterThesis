"""Environment Interface (R12, R15): the action space T, exactly four operations.

  listZones                          -> zones with adjacency            (observation)
  listDevices(zoneId)                -> devices with supportedCommand   (observation)
  getDeviceState(deviceId)           -> current state                   (observation)
  invokeCommand(deviceId, command, value) -> outcome, resulting state   (the only actuation)

Every call goes through `execute`, which checks, in this order: operation in the
allow-list, arguments valid for the operation (C3), zone/device known, inside the scope
negotiated at binding, command in the device's `supportedCommand`. A rejected call never
reaches the environment and always comes back as `ToolResult(ok=False, error=...)`.
"""

from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from cpsagent.binding import BoundSession
from cpsagent.contracts import Operation, ToolCall, ToolCallAdapter, ToolError, ToolResult
from cpsagent.contracts.tool import (
    GetDeviceStateCall,
    InvokeCommandCall,
    ListDevicesCall,
    ListZonesCall,
)
from cpsagent.environment import Device, DeviceFailure, InvalidValue

# The allow-list, in code. Adding an operation here is a change to the thesis' action space.
ALLOWED_OPERATIONS: frozenset[Operation] = frozenset(
    {
        Operation.LIST_ZONES,
        Operation.LIST_DEVICES,
        Operation.GET_DEVICE_STATE,
        Operation.INVOKE_COMMAND,
    }
)
# The only operation that changes the environment.
MUTATING_OPERATIONS: frozenset[Operation] = frozenset({Operation.INVOKE_COMMAND})


def _fail(operation: Operation | None, error: ToolError) -> ToolResult:
    return ToolResult(ok=False, operation=operation, error=error)


class EnvironmentInterface:
    def __init__(self, session: BoundSession) -> None:
        """R11: configured by injecting the bound session (broker, token, scope)."""
        self._session = session
        self._broker = session.broker
        self._token = session.token
        self._handlers: dict[Operation, Callable[[Any], ToolResult]] = {
            Operation.LIST_ZONES: self._list_zones,
            Operation.LIST_DEVICES: self._list_devices,
            Operation.GET_DEVICE_STATE: self._get_device_state,
            Operation.INVOKE_COMMAND: self._invoke_command,
        }

    # --- single entry point -------------------------------------------------------------

    def execute(self, call: ToolCall | dict[str, Any]) -> ToolResult:
        """Run one call. Accepts a C3 model or raw JSON-like data (e.g. from a planner)."""
        if not self._session.bound:
            raise RuntimeError("session is not bound")
        if isinstance(call, dict):
            name = call.get("operation")
            if name not in {op.value for op in ALLOWED_OPERATIONS}:
                return _fail(None, ToolError.OPERATION_NOT_ALLOWED)
            try:
                call = ToolCallAdapter.validate_python(call)
            except ValidationError:
                return _fail(Operation(name), ToolError.INVALID_ARGS)
        if call.operation not in ALLOWED_OPERATIONS:  # defence in depth for typed calls
            return _fail(None, ToolError.OPERATION_NOT_ALLOWED)
        return self._handlers[call.operation](call)

    # --- convenience wrappers (same path as execute) ------------------------------------

    def list_zones(self) -> ToolResult:
        return self.execute({"operation": "listZones"})

    def list_devices(self, zone_id: str) -> ToolResult:
        return self.execute({"operation": "listDevices", "args": {"zoneId": zone_id}})

    def get_device_state(self, device_id: str) -> ToolResult:
        return self.execute({"operation": "getDeviceState", "args": {"deviceId": device_id}})

    def invoke_command(self, device_id: str, command: str, value: Any = None) -> ToolResult:
        args = {"deviceId": device_id, "command": command, "value": value}
        return self.execute({"operation": "invokeCommand", "args": args})

    # --- handlers -----------------------------------------------------------------------

    def _list_zones(self, call: ListZonesCall) -> ToolResult:
        zones = [
            {"zoneId": z.zone_id, "name": z.name, "adjacency": list(z.adjacency)}
            for z in self._broker.zones(self._token)
        ]
        return ToolResult(ok=True, operation=call.operation, state=zones)

    def _list_devices(self, call: ListDevicesCall) -> ToolResult:
        zone_id = call.args.zone_id
        if zone_id not in self._session.spatial_model.zones:
            return _fail(call.operation, ToolError.UNKNOWN_ZONE)
        if zone_id not in self._session.scope_zones:
            return _fail(call.operation, ToolError.OUT_OF_SCOPE)
        devices = [
            {
                "deviceId": d.device_id,
                "category": d.category,
                "controlledProperty": d.controlled_property,
                "supportedCommand": list(d.supported_command),
            }
            for d in self._broker.devices(self._token, zone_id)
        ]
        return ToolResult(ok=True, operation=call.operation, state=devices)

    def _device_in_scope(self, operation: Operation, device_id: str) -> Device | ToolResult:
        device = self._broker.device(self._token, device_id)
        if device is None:
            return _fail(operation, ToolError.UNKNOWN_DEVICE)
        if device.ref_zone not in self._session.scope_zones:
            return _fail(operation, ToolError.OUT_OF_SCOPE)
        return device

    def _get_device_state(self, call: GetDeviceStateCall) -> ToolResult:
        device = self._device_in_scope(call.operation, call.args.device_id)
        if isinstance(device, ToolResult):
            return device
        state = {"deviceId": device.device_id, **device.state}
        return ToolResult(ok=True, operation=call.operation, state=state)

    def _invoke_command(self, call: InvokeCommandCall) -> ToolResult:
        args = call.args
        device = self._device_in_scope(call.operation, args.device_id)
        if isinstance(device, ToolResult):
            return device
        if args.command not in device.supported_command:
            return _fail(call.operation, ToolError.COMMAND_NOT_SUPPORTED)
        try:
            new_state = self._broker.execute(
                self._token, device.device_id, args.command, args.value
            )
        except InvalidValue:
            return _fail(call.operation, ToolError.INVALID_ARGS)
        except DeviceFailure:
            return _fail(call.operation, ToolError.DEVICE_FAILURE)
        state = {"deviceId": device.device_id, **new_state}
        return ToolResult(ok=True, operation=call.operation, state=state)
