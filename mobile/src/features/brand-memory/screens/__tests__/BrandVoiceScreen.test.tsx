import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { Alert } from "react-native";
import { BrandVoiceScreen } from "../BrandVoiceScreen";
import { deleteAllBrands } from "../../../brand/services/brand.service";
import { getBrandVoice } from "../../services/brandMemory.service";

const mockReplace = jest.fn();
const mockDismissTo = jest.fn();
const mockBack = jest.fn();
const mockPush = jest.fn();
const mockConfirm = jest.fn<
  (title: string, message: string, options?: unknown) => Promise<boolean>
>();

jest.mock("expo-router", () => ({
  useLocalSearchParams: () => ({ brandId: "brand-1" }),
  useRouter: () => ({
    replace: mockReplace,
    dismissTo: mockDismissTo,
    back: mockBack,
    push: mockPush,
  }),
}));

jest.mock("../../../../lib/confirm", () => ({
  confirmAsync: (title: string, message: string, options?: unknown) =>
    mockConfirm(title, message, options),
}));

jest.mock("../../../brand/services/brand.service", () => ({
  deleteAllBrands: jest.fn(),
}));

jest.mock("../../services/brandMemory.service", () => ({
  getBrandVoice: jest.fn(),
  saveBrandVoice: jest.fn(),
}));

const deleteAllBrandsMock = jest.mocked(deleteAllBrands);
const getBrandVoiceMock = jest.mocked(getBrandVoice);

const alertSpy = jest.spyOn(Alert, "alert").mockImplementation(() => {});

describe("BrandVoiceScreen delete all brands", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockConfirm.mockResolvedValue(true);
    getBrandVoiceMock.mockResolvedValue({
      brand: "brand-1",
      tone: "Friendly",
      target_audience: "",
      language: "English",
      writing_guidelines: "",
      example_content: "",
    });
    deleteAllBrandsMock.mockResolvedValue({
      deleted: 2,
      counts: { brands: 2 },
    });
  });

  it("deletes all brands after confirmation and returns to the empty brand list", async () => {
    const { findByLabelText } = await render(<BrandVoiceScreen />);

    fireEvent.press(await findByLabelText(/^Delete all brands\./));

    await waitFor(() => {
      expect(deleteAllBrandsMock).toHaveBeenCalledTimes(1);
    });
    expect(mockConfirm).toHaveBeenCalledWith(
      "Delete all brands?",
      expect.stringContaining("permanently deleted"),
      expect.objectContaining({ destructive: true })
    );
    expect(alertSpy).toHaveBeenCalledWith(
      "Brands deleted",
      expect.stringContaining("permanently deleted")
    );
    await waitFor(() => {
      expect(mockDismissTo).toHaveBeenCalledWith({
        pathname: "/brand-memory",
        params: { deleted: "all" },
      });
    });
  });

  it("does not delete anything when the confirmation is dismissed", async () => {
    mockConfirm.mockResolvedValue(false);
    const { findByLabelText } = await render(<BrandVoiceScreen />);

    fireEvent.press(await findByLabelText(/^Delete all brands\./));

    await waitFor(() => {
      expect(mockConfirm).toHaveBeenCalled();
    });
    expect(deleteAllBrandsMock).not.toHaveBeenCalled();
    expect(mockDismissTo).not.toHaveBeenCalled();
  });

  it("shows the error and stays on the brand when deletion fails", async () => {
    deleteAllBrandsMock.mockRejectedValue(new Error("Deletion failed safely."));
    const { findByLabelText } = await render(<BrandVoiceScreen />);

    fireEvent.press(await findByLabelText(/^Delete all brands\./));

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith(
        "Couldn’t delete brands",
        "Deletion failed safely."
      );
    });
    expect(mockDismissTo).not.toHaveBeenCalled();
  });
});
