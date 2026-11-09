import { describe, expect, it, jest } from "@jest/globals";
import { fireEvent, render } from "@testing-library/react-native";
import { StudioText } from "../StudioText";

describe("studio typography", () => {
  it("renders editorial page headings with readable olive text", async () => {
    const screen = await render(<StudioText variant="page" tone="olive">Brand Memory</StudioText>);
    expect(screen.getByText("Brand Memory")).toHaveStyle({
      fontSize: 22, lineHeight: 30, fontWeight: "600", color: "#25221F",
    });
  });

  it("keeps body text distinct from controls and captions", async () => {
    const screen = await render(<StudioText variant="body" tone="secondary">Your content</StudioText>);
    expect(screen.getByText("Your content")).toHaveStyle({
      fontSize: 14, lineHeight: 21, color: "#25221F",
    });
  });

  it("forwards existing text interactions and accessibility props", async () => {
    const press = jest.fn();
    const screen = await render(
      <StudioText onPress={press} accessibilityLabel="Read details" allowFontScaling>Details</StudioText>,
    );
    const text = screen.getByLabelText("Read details");
    await fireEvent.press(text);
    expect(press).toHaveBeenCalledTimes(1);
    expect(text.props.allowFontScaling).toBe(true);
  });
});
