"""C3 - Tool call and result (R12): the action space T of the Environment Interface."""

from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import Field, TypeAdapter, model_validator

from .base import Contract
from .plan import CommandValue


class Operation(StrEnum):
    """Exactly the four allowed operations. Only INVOKE_COMMAND changes the environment."""

    LIST_ZONES = "listZones"
    LIST_DEVICES = "listDevices"
    GET_DEVICE_STATE = "getDeviceState"
    INVOKE_COMMAND = "invokeCommand"


class NoArgs(Contract):
    pass


class ListDevicesArgs(Contract):
    zone_id: str = Field(min_length=1)


class GetDeviceStateArgs(Contract):
    device_id: str = Field(min_length=1)


class InvokeCommandArgs(Contract):
    device_id: str = Field(min_length=1)
    command: str = Field(min_length=1)
    value: CommandValue = None


# One call model per operation, so the arguments are checked against the operation.
class ListZonesCall(Contract):
    operation: Literal[Operation.LIST_ZONES]
    args: NoArgs = NoArgs()


class ListDevicesCall(Contract):
    operation: Literal[Operation.LIST_DEVICES]
    args: ListDevicesArgs


class GetDeviceStateCall(Contract):
    operation: Literal[Operation.GET_DEVICE_STATE]
    args: GetDeviceStateArgs


class InvokeCommandCall(Contract):
    operation: Literal[Operation.INVOKE_COMMAND]
    args: InvokeCommandArgs


# Any operation name outside the enum fails validation; the Environment Interface
# turns that failure into ToolResult(ok=False, error="operation_not_allowed").
ToolCall = Annotated[
    ListZonesCall | ListDevicesCall | GetDeviceStateCall | InvokeCommandCall,
    Field(discriminator="operation"),
]
ToolCallAdapter: TypeAdapter[ToolCall] = TypeAdapter(ToolCall)


class ToolError(StrEnum):
    OPERATION_NOT_ALLOWED = "operation_not_allowed"
    INVALID_ARGS = "invalid_args"
    UNKNOWN_ZONE = "unknown_zone"
    UNKNOWN_DEVICE = "unknown_device"
    COMMAND_NOT_SUPPORTED = "command_not_supported"
    OUT_OF_SCOPE = "out_of_scope"  # device outside the negotiated scope
    DEVICE_FAILURE = "device_failure"  # command accepted but the device did not execute it


class ToolResult(Contract):
    """Result of one operation.

    `state` is the observation: zones with adjacency (listZones), devices
    (listDevices), or a device state (getDeviceState / invokeCommand).
    `operation` is None only for a rejected call whose operation is not one of the four.
    """

    ok: bool
    operation: Operation | None
    state: dict[str, Any] | list[dict[str, Any]] | None = None
    error: ToolError | None = None

    @model_validator(mode="after")
    def _ok_xor_error(self) -> Self:
        if self.ok and self.error is not None:
            raise ValueError("a successful result has no error")
        if not self.ok and self.error is None:
            raise ValueError("a failed result must carry an error")
        if self.operation is None and self.error is not ToolError.OPERATION_NOT_ALLOWED:
            raise ValueError("operation may be null only when it was not allowed")
        return self
