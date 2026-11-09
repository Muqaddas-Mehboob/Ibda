import {
  createContext,
  forwardRef,
  useContext,
  useEffect,
  useState,
  type PropsWithChildren,
  type ComponentRef,
} from "react";
import {
  AccessibilityInfo,
  Animated,
  Easing,
  Platform,
  Pressable,
  StyleSheet,
  TextInput,
  useAnimatedValue,
  View,
  type PressableProps,
  type TextInputProps,
  type ViewProps,
} from "react-native";
import { cssInterop } from "nativewind";

// Motion preferences live here, independently of authentication and app data.
const ReducedMotion = createContext(true);
const InputFrameFocus = createContext<((value: number) => void) | null>(null);

export function StudioMotionProvider({ children }: PropsWithChildren) {
  const [reduced, setReduced] = useState(true);

  useEffect(() => {
    let mounted = true;
    let preferenceChanged = false;
    const subscription = AccessibilityInfo.addEventListener(
      "reduceMotionChanged",
      (value) => {
        preferenceChanged = true;
        if (mounted) setReduced(value);
      },
    );
    void AccessibilityInfo.isReduceMotionEnabled().then(
      (value) => {
        if (mounted && !preferenceChanged) setReduced(value);
      },
      () => {},
    );
    return () => {
      mounted = false;
      subscription.remove();
    };
  }, []);

  return <ReducedMotion.Provider value={reduced}>{children}</ReducedMotion.Provider>;
}

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);
const AnimatedInput = Animated.createAnimatedComponent(TextInput);
cssInterop(AnimatedPressable, { className: "style" });
cssInterop(AnimatedInput, { className: "style" });
cssInterop(Animated.View, { className: "style" });

type StudioPressableProps = PressableProps & { className?: string };

export const StudioPressable = forwardRef<ComponentRef<typeof Pressable>, StudioPressableProps>(
  function StudioPressable(
    { onPressIn, onPressOut, onHoverIn, onHoverOut, style, disabled, ...props },
    ref,
  ) {
    const reduced = useContext(ReducedMotion);
    const scale = useAnimatedValue(1);
    const [pressed, setPressed] = useState(false);
    const [hovered, setHovered] = useState(false);
    const resolvedStyle = typeof style === "function" ? style({ pressed, hovered }) : style;
    const existingTransform = StyleSheet.flatten(resolvedStyle)?.transform;

    useEffect(() => {
      if (reduced || disabled) {
        scale.stopAnimation();
        scale.setValue(1);
      }
      return () => scale.stopAnimation();
    }, [disabled, reduced, scale]);

    const animate = (value: number) => {
      scale.stopAnimation();
      Animated.timing(scale, {
        toValue: reduced || disabled ? 1 : value,
        duration: reduced ? 0 : value < 1 ? 120 : 180,
        easing: Easing.out(Easing.quad),
        useNativeDriver: Platform.OS !== "web",
        isInteraction: false,
      }).start();
    };

    return (
      <AnimatedPressable
        {...props}
        ref={ref}
        disabled={disabled}
        onPressIn={(event) => {
          setPressed(true);
          animate(0.97);
          onPressIn?.(event);
        }}
        onPressOut={(event) => {
          setPressed(false);
          animate(1);
          onPressOut?.(event);
        }}
        onHoverIn={(event) => {
          setHovered(true);
          onHoverIn?.(event);
        }}
        onHoverOut={(event) => {
          setHovered(false);
          onHoverOut?.(event);
        }}
        style={[
          resolvedStyle,
          pressed && !disabled && { opacity: 0.84 },
          hovered && !pressed && !disabled && { opacity: 0.94 },
          { transform: [...(Array.isArray(existingTransform) ? existingTransform : []), { scale }] },
        ]}
      />
    );
  },
);

export const StudioInput = forwardRef<ComponentRef<typeof TextInput>, TextInputProps & { className?: string }>(
  function StudioInput({ onFocus, onBlur, style, editable, multiline, ...props }, ref) {
    const reduced = useContext(ReducedMotion);
    const frameFocus = useContext(InputFrameFocus);
    const focus = useAnimatedValue(0);

    useEffect(() => () => focus.stopAnimation(), [focus]);

    const animate = (value: number) => {
      focus.stopAnimation();
      Animated.timing(focus, {
        toValue: value,
        duration: reduced ? 0 : 160,
        easing: Easing.out(Easing.quad),
        useNativeDriver: false,
        isInteraction: false,
      }).start();
    };

    return (
      <AnimatedInput
        {...props}
        ref={ref}
        multiline={multiline}
        editable={editable}
        onFocus={(event) => {
          animate(1);
          frameFocus?.(1);
          onFocus?.(event);
        }}
        onBlur={(event) => {
          animate(0);
          frameFocus?.(0);
          onBlur?.(event);
        }}
        style={[
          styles.input,
          !multiline && styles.singleLineInput,
          editable === false && styles.disabledInput,
          style,
          frameFocus ? styles.insetInput : {
            borderColor: focus.interpolate({
              inputRange: [0, 1],
              outputRange: ["#E9E2DA", "#C24A3C"],
            }),
          },
        ]}
      />
    );
  },
);

export function StudioInputFrame({ style, children, ...props }: ViewProps & { className?: string }) {
  const reduced = useContext(ReducedMotion);
  const focus = useAnimatedValue(0);
  useEffect(() => () => focus.stopAnimation(), [focus]);
  const animate = (value: number) => {
    focus.stopAnimation();
    Animated.timing(focus, {
      toValue: value,
      duration: reduced ? 0 : 160,
      useNativeDriver: false,
      isInteraction: false,
    }).start();
  };
  return (
    <InputFrameFocus.Provider value={animate}>
      <Animated.View
        {...props}
        style={[style, styles.inputFrame, {
          borderColor: focus.interpolate({ inputRange: [0, 1], outputRange: ["#E9E2DA", "#C24A3C"] }),
        }]}
      >
        {children}
      </Animated.View>
    </InputFrameFocus.Provider>
  );
}

export function StudioCard({ style, ...props }: ViewProps & { className?: string }) {
  return <View {...props} style={[styles.card, style]} />;
}

export function StudioHighlight({ selected, color = "#F1E9DF" }: { selected: boolean; color?: string }) {
  const reduced = useContext(ReducedMotion);
  const opacity = useAnimatedValue(selected ? 1 : 0);
  useEffect(() => {
    Animated.timing(opacity, {
      toValue: selected ? 1 : 0,
      duration: reduced ? 0 : 180,
      easing: Easing.out(Easing.quad),
      useNativeDriver: Platform.OS !== "web",
      isInteraction: false,
    }).start();
    return () => opacity.stopAnimation();
  }, [opacity, reduced, selected]);
  return (
    <Animated.View
      pointerEvents="none"
      accessible={false}
      style={[StyleSheet.absoluteFill, styles.tabHighlight, { opacity, backgroundColor: color }]}
    />
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 24,
    shadowColor: "#292724",
    shadowOpacity: 0.045,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 6 },
    elevation: 2,
  },
  input: {
    borderRadius: 18,
    borderWidth: 1,
    backgroundColor: "#F7F4EF",
    color: "#292724",
    fontSize: 16,
    lineHeight: 24,
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  singleLineInput: { minHeight: 56 },
  disabledInput: { opacity: 0.58 },
  inputFrame: { borderRadius: 18, borderWidth: 1, backgroundColor: "#F7F4EF", paddingHorizontal: 16 },
  insetInput: { borderWidth: 0, backgroundColor: "transparent", paddingHorizontal: 0 },
  tabHighlight: { borderRadius: 18, backgroundColor: "#F1E9DF" },
});
