import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { fireEvent, render } from "@testing-library/react-native";
import { StudioFonts } from "../StudioFonts";
import { StudioText } from "../StudioText";

const mockUseFonts = jest.fn<() => [boolean, Error | null]>();
jest.mock("expo-font", () => ({ useFonts: () => mockUseFonts() }));

beforeEach(() => { mockUseFonts.mockReturnValue([true, null]); });

describe("local Raleway presentation", () => {
  it("uses the bundled semibold face for page headings", async () => {
    const screen = await render(<StudioFonts><StudioText variant="page">Workspace</StudioText></StudioFonts>);
    expect(screen.getByText("Workspace")).toHaveStyle({ fontFamily: "RalewaySemiBold", fontSize: 22 });
  });

  it("keeps content and interactions available while font assets load", async () => {
    mockUseFonts.mockReturnValue([false, null]);
    const press = jest.fn();
    const screen = await render(<StudioFonts><StudioText onPress={press}>Continue</StudioText></StudioFonts>);
    await fireEvent.press(screen.getByText("Continue"));
    expect(press).toHaveBeenCalledTimes(1);
  });

  it("uses the regular face for body copy and the semibold face for controls", async () => {
    const screen = await render(<StudioFonts><StudioText variant="body">Description</StudioText><StudioText variant="button">Save</StudioText></StudioFonts>);
    expect(screen.getByText("Description")).toHaveStyle({ fontFamily: "RalewayRegular" });
    expect(screen.getByText("Save")).toHaveStyle({ fontFamily: "RalewaySemiBold" });
  });
});
