import { afterEach, describe, expect, it, jest } from "@jest/globals";
import { act, fireEvent, render } from "@testing-library/react-native";
import { AccessibilityInfo, Animated, Text } from "react-native";
import {
  StudioInput,
  StudioInputFrame,
  StudioMotionProvider,
  StudioPressable,
} from "../StudioControls";

afterEach(() => { jest.restoreAllMocks(); });

describe("presentation controls preserve existing interactions", () => {
  it("forwards the original press and press lifecycle handlers once", async () => {
    const press = jest.fn();
    const pressIn = jest.fn();
    const pressOut = jest.fn();
    const screen = await render(
      <StudioPressable onPress={press} onPressIn={pressIn} onPressOut={pressOut}>
        <Text>Save draft</Text>
      </StudioPressable>,
    );
    const button = screen.getByText("Save draft");
    await fireEvent(button, "pressIn", { nativeEvent: {} });
    await fireEvent.press(button);
    await fireEvent(button, "pressOut", { nativeEvent: {} });
    expect(press).toHaveBeenCalledTimes(1);
    expect(pressIn).toHaveBeenCalledTimes(1);
    expect(pressOut).toHaveBeenCalledTimes(1);
  });

  it("keeps a disabled control disabled", async () => {
    const press = jest.fn();
    const screen = await render(
      <StudioPressable disabled onPress={press}>
        <Text>Checkout</Text>
      </StudioPressable>,
    );
    await fireEvent.press(screen.getByText("Checkout"));
    expect(press).not.toHaveBeenCalled();
  });

  it("preserves controlled text, secure entry, and focus callbacks inside a frame", async () => {
    const change = jest.fn();
    const focus = jest.fn();
    const blur = jest.fn();
    const screen = await render(
      <StudioInputFrame>
        <StudioInput
          accessibilityLabel="Password"
          value="original"
          secureTextEntry
          onChangeText={change}
          onFocus={focus}
          onBlur={blur}
        />
      </StudioInputFrame>,
    );
    const input = screen.getByLabelText("Password");
    await fireEvent.changeText(input, "edited");
    await fireEvent(input, "focus", { nativeEvent: {} });
    await fireEvent(input, "blur", { nativeEvent: {} });
    expect(change).toHaveBeenCalledWith("edited");
    expect(input.props.value).toBe("original");
    expect(input.props.secureTextEntry).toBe(true);
    expect(focus).toHaveBeenCalledTimes(1);
    expect(blur).toHaveBeenCalledTimes(1);
  });

  it("disables motion when the system requests Reduced Motion", async () => {
    jest.spyOn(AccessibilityInfo, "isReduceMotionEnabled").mockResolvedValue(true);
    const timing = jest.spyOn(Animated, "timing");
    const screen = await render(
      <StudioMotionProvider>
        <StudioPressable><Text>Continue</Text></StudioPressable>
      </StudioMotionProvider>,
    );
    await act(async () => {});
    await fireEvent(screen.getByText("Continue"), "pressIn", { nativeEvent: {} });
    expect(timing).toHaveBeenLastCalledWith(
      expect.anything(),
      expect.objectContaining({ duration: 0, toValue: 1 }),
    );
  });

  it("uses visible press feedback and a smooth release when motion is enabled", async () => {
    jest.spyOn(AccessibilityInfo, "isReduceMotionEnabled").mockResolvedValue(false);
    const timing = jest.spyOn(Animated, "timing");
    const screen = await render(
      <StudioMotionProvider>
        <StudioPressable><Text>Generate</Text></StudioPressable>
      </StudioMotionProvider>,
    );
    await fireEvent(screen.getByText("Generate"), "pressIn", { nativeEvent: {} });
    expect(timing).toHaveBeenLastCalledWith(
      expect.anything(),
      expect.objectContaining({ duration: 120, toValue: 0.97 }),
    );
    await fireEvent(screen.getByText("Generate"), "pressOut", { nativeEvent: {} });
    expect(timing).toHaveBeenLastCalledWith(
      expect.anything(),
      expect.objectContaining({ duration: 180, toValue: 1 }),
    );
  });

  it("keeps a visible held state without triggering or replacing an action", async () => {
    const press = jest.fn();
    const longPress = jest.fn();
    const screen = await render(
      <StudioPressable testID="held-button" onPress={press} onLongPress={longPress}>
        <Text>Hold</Text>
      </StudioPressable>,
    );
    const button = screen.getByTestId("held-button");
    await fireEvent(button, "pressIn", { nativeEvent: {} });
    expect(button).toHaveStyle({ opacity: 0.84 });
    expect(press).not.toHaveBeenCalled();
    await fireEvent(button, "longPress", { nativeEvent: {} });
    expect(longPress).toHaveBeenCalledTimes(1);
    await fireEvent(button, "pressOut", { nativeEvent: {} });
    expect(button).not.toHaveStyle({ opacity: 0.84 });
  });
});
