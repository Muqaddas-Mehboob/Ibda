import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { Alert } from "react-native";
import { BrandVoiceBlueprintScreen } from "../BrandVoiceBlueprintScreen";
import {
  deleteBrand,
  getBrand,
} from "../../../brand/services/brand.service";
import { getBrandVoice } from "../../services/brandMemory.service";

const mockReplace = jest.fn();
const mockDismissTo = jest.fn();
const mockBack = jest.fn();
const mockConfirm = jest.fn<
  (title: string, message: string, options?: unknown) => Promise<boolean>
>();

jest.mock("expo-router", () => ({
  useLocalSearchParams: () => ({ brandId: "brand-1" }),
  useRouter: () => ({
    replace: mockReplace,
    dismissTo: mockDismissTo,
    back: mockBack,
  }),
}));

jest.mock("../../../../lib/confirm", () => ({
  confirmAsync: (title: string, message: string, options?: unknown) =>
    mockConfirm(title, message, options),
}));

jest.mock("../../../brand/services/brand.service", () => ({
  getBrand: jest.fn(),
  deleteBrand: jest.fn(),
}));

jest.mock("../../services/brandMemory.service", () => ({
  getBrandVoice: jest.fn(),
}));

const getBrandMock = jest.mocked(getBrand);
const deleteBrandMock = jest.mocked(deleteBrand);
const getBrandVoiceMock = jest.mocked(getBrandVoice);

const alertSpy = jest.spyOn(Alert, "alert").mockImplementation(() => {});

const brand = {
  id: "brand-1",
  name: "Acme Studio",
  industry: "Design",
  description: "",
  website: "",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const voice = {
  brand: "brand-1",
  tone: "Bold",
  target_audience: "Founders",
  language: "English",
  writing_guidelines: "",
  example_content: "",
};

describe("BrandVoiceBlueprintScreen brand deletion", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockConfirm.mockResolvedValue(true);
    getBrandMock.mockResolvedValue(brand);
    getBrandVoiceMock.mockResolvedValue(voice);
    deleteBrandMock.mockResolvedValue({
      deleted: 1,
      counts: { brands: 1, brand_voices: 1 },
    });
  });

  it("deletes only the current brand after confirmation and returns to the brand list", async () => {
    const { findByLabelText } = await render(<BrandVoiceBlueprintScreen />);

    const button = await findByLabelText(/^Delete current brand\./);
    fireEvent.press(button);

    await waitFor(() => {
      expect(deleteBrandMock).toHaveBeenCalledWith("brand-1");
    });
    expect(mockConfirm).toHaveBeenCalledWith(
      "Delete this brand?",
      expect.stringContaining("Acme Studio"),
      expect.objectContaining({ destructive: true })
    );
    expect(deleteBrandMock).toHaveBeenCalledTimes(1);
    expect(alertSpy).toHaveBeenCalledWith(
      "Brand deleted",
      expect.stringContaining("Acme Studio")
    );
    await waitFor(() => {
      expect(mockDismissTo).toHaveBeenCalledWith({
        pathname: "/brand-memory",
        params: { deleted: "1" },
      });
    });
  });

  it("does not delete anything when the confirmation is dismissed", async () => {
    mockConfirm.mockResolvedValue(false);
    const { findByLabelText } = await render(<BrandVoiceBlueprintScreen />);

    fireEvent.press(await findByLabelText(/^Delete current brand\./));

    await waitFor(() => {
      expect(mockConfirm).toHaveBeenCalled();
    });
    expect(deleteBrandMock).not.toHaveBeenCalled();
    expect(mockDismissTo).not.toHaveBeenCalled();
  });

  it("shows the backend error and keeps the blueprint when deletion fails", async () => {
    deleteBrandMock.mockRejectedValue(new Error("Deletion failed safely."));
    const { findByLabelText } = await render(<BrandVoiceBlueprintScreen />);

    fireEvent.press(await findByLabelText(/^Delete current brand\./));

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith(
        "Couldn’t delete brand",
        "Deletion failed safely."
      );
    });
    expect(mockDismissTo).not.toHaveBeenCalled();
  });

  it("ignores repeated presses while the deletion is in progress", async () => {
    let resolveDeletion:
      | ((value: { deleted: number; counts: Record<string, number> }) => void)
      | undefined;
    deleteBrandMock.mockReturnValue(
      new Promise<{ deleted: number; counts: Record<string, number> }>(
        (resolve) => {
          resolveDeletion = resolve;
        }
      )
    );
    const { findByLabelText, getByLabelText, getByText } = await render(
      <BrandVoiceBlueprintScreen />
    );

    const button = await findByLabelText(/^Delete current brand\./);
    fireEvent.press(button);

    await waitFor(() => {
      expect(deleteBrandMock).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(getByText("Deleting brand...")).toBeTruthy();
    });

    fireEvent.press(getByLabelText(/^Delete current brand\./));
    expect(deleteBrandMock).toHaveBeenCalledTimes(1);

    resolveDeletion?.({ deleted: 1, counts: { brands: 1 } });
    await waitFor(() => {
      expect(mockDismissTo).toHaveBeenCalled();
    });
  });
});
