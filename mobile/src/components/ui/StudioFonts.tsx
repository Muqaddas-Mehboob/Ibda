import { createContext, useContext, type PropsWithChildren } from "react";
import { Platform, type TextStyle } from "react-native";
import { useFonts } from "expo-font";

const FontReady = createContext(false);

export function StudioFonts({ children }: PropsWithChildren) {
  const [loaded] = useFonts({
    RalewayRegular: require("../../../assets/fonts/Raleway-Regular.ttf"),
    RalewayMedium: require("../../../assets/fonts/Raleway-Medium.ttf"),
    RalewaySemiBold: require("../../../assets/fonts/Raleway-SemiBold.ttf"),
    RalewayBold: require("../../../assets/fonts/Raleway-Bold.ttf"),
  });

  // Loading a visual asset never blocks authentication, navigation, or input.
  return <FontReady.Provider value={loaded}>{children}</FontReady.Provider>;
}

export function useStudioFont(weight: TextStyle["fontWeight"] = "400"): TextStyle {
  const ready = useContext(FontReady);
  const numeric = weight === "bold" ? 700 : weight === "normal" ? 400 : Number(weight);
  const family = numeric >= 700 ? "RalewayBold" : numeric >= 600 ? "RalewaySemiBold"
    : numeric >= 500 ? "RalewayMedium" : "RalewayRegular";
  return ready
    ? { fontFamily: family, fontWeight: "normal" }
    : { fontFamily: Platform.select({ ios: "System", android: "sans-serif", default: "system-ui" }), fontWeight: weight };
}
