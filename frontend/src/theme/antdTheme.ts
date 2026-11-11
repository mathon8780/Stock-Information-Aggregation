import { theme as algorithms, type ThemeConfig } from 'antd';
import type { ThemeMode } from './ThemeModeContext';

export function createAntdTheme(mode: ThemeMode): ThemeConfig {
  const dark = mode === 'dark';
  const panel = dark ? '#202732' : '#ffffff',
    raised = dark ? '#272f3c' : '#f5f6f8',
    line = dark ? '#384150' : '#d9dfe6';
  return {
    algorithm: dark ? algorithms.darkAlgorithm : algorithms.defaultAlgorithm,
    token: {
      colorPrimary: dark ? '#eac276' : '#876017',
      colorInfo: dark ? '#9ab9ec' : '#3869a5',
      colorSuccess: dark ? '#62d9b4' : '#168260',
      colorWarning: dark ? '#eac276' : '#876017',
      colorError: dark ? '#ff8f9b' : '#c73e50',
      colorBgLayout: dark ? '#171c24' : '#f0f2f5',
      colorBgContainer: panel,
      colorTextBase: dark ? '#e7eaf0' : '#26313d',
      colorTextSecondary: dark ? '#a5afbf' : '#65717e',
      colorBorder: line,
      colorBorderSecondary: line,
      borderRadius: 3,
      borderRadiusLG: 3,
      controlHeight: 32,
      fontSize: 13,
      fontFamily: '"Segoe UI", "Microsoft YaHei", sans-serif',
    },
    components: {
      Button: { defaultShadow: 'none', primaryShadow: 'none' },
      Card: { headerBg: panel, paddingLG: 16 },
      Table: { headerBg: raised, rowHoverBg: raised, borderColor: line },
      Layout: { bodyBg: dark ? '#171c24' : '#f0f2f5', headerBg: panel },
      Tag: { borderRadiusSM: 3 },
      Segmented: { itemSelectedBg: dark ? '#4c4230' : '#f3e8d0' },
    },
  };
}
export default createAntdTheme('light');
