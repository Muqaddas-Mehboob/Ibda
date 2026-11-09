import { Platform, StyleSheet, Text, type TextProps } from 'react-native';

import { Fonts, ThemeColor } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { useStudioFont } from './ui/StudioFonts';

export type ThemedTextProps = TextProps & {
  type?: 'default' | 'title' | 'small' | 'smallBold' | 'subtitle' | 'link' | 'linkPrimary' | 'code';
  themeColor?: ThemeColor;
};

export function ThemedText({ style, type = 'default', themeColor, ...rest }: ThemedTextProps) {
  const theme = useTheme();
  const font = useStudioFont(StyleSheet.flatten([styles[type], style])?.fontWeight);

  return <Text style={[{ color: theme[themeColor ?? 'text'] }, styles[type], style, type !== 'code' && font]} {...rest} />;
}

const styles = StyleSheet.create({
  small: {
    fontSize: 14,
    lineHeight: 20,
    fontWeight: 500,
  },
  smallBold: {
    fontSize: 14,
    lineHeight: 20,
    fontWeight: 700,
  },
  default: {
    fontSize: 16,
    lineHeight: 24,
    fontWeight: 500,
  },
  title: {
    fontSize: 30,
    fontWeight: 600,
    lineHeight: 38,
  },
  subtitle: {
    fontSize: 24,
    lineHeight: 32,
    fontWeight: 600,
  },
  link: {
    fontWeight: 400,
    lineHeight: 30,
    fontSize: 14,
  },
  linkPrimary: {
    fontWeight: 400,
    lineHeight: 30,
    fontSize: 14,
    color: '#C24A3C',
  },
  code: {
    fontFamily: Fonts.mono,
    fontWeight: Platform.select({ android: 700 }) ?? 500,
    fontSize: 12,
  },
});
