import type { ThemeConfig } from 'antd';

const antdTheme: ThemeConfig = {
  token: {
    colorPrimary: '#0f766e',
    colorInfo: '#2563eb',
    colorSuccess: '#087f5b',
    colorWarning: '#b7791f',
    colorError: '#cf222e',
    colorBgLayout: '#edf2f5',
    colorBgContainer: '#ffffff',
    colorTextBase: '#16232d',
    colorTextSecondary: '#60707b',
    colorBorderSecondary: '#d7e0e6',
    borderRadius: 8,
    borderRadiusLG: 8,
    controlHeight: 36,
    fontFamily: 'Bahnschrift, "Microsoft YaHei UI", "Segoe UI", sans-serif',
  },
  components: {
    Alert: { borderRadiusLG: 8 },
    Button: {
      borderRadius: 8,
      controlHeight: 36,
      defaultShadow: 'none',
      primaryShadow: 'none',
    },
    Card: {
      borderRadiusLG: 8,
      headerBg: '#ffffff',
      paddingLG: 20,
    },
    Layout: {
      bodyBg: '#edf2f5',
      headerBg: '#f8fafb',
      siderBg: '#111c22',
    },
    Menu: {
      darkItemBg: 'transparent',
      darkItemColor: '#b8c5ca',
      darkItemHoverBg: '#172932',
      darkItemHoverColor: '#ffffff',
      darkItemSelectedBg: '#0f766e',
      darkItemSelectedColor: '#ffffff',
      itemBorderRadius: 8,
    },
    Table: {
      borderColor: '#dce5ea',
      headerBg: '#f4f7f9',
      headerColor: '#42515c',
      rowHoverBg: '#f2f8f7',
    },
    Tag: { borderRadiusSM: 6 },
  },
};

export default antdTheme;
