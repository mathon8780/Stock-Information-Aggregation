import { AuditOutlined, CloseCircleOutlined, DeleteOutlined, LineChartOutlined, LoginOutlined, PlusOutlined, ReloadOutlined, SafetyCertificateOutlined, ShoppingCartOutlined, SyncOutlined, UserAddOutlined, WalletOutlined } from '@ant-design/icons';
import { AutoComplete, Button, Card, Col, Empty, Form, Input, InputNumber, Modal, Popconfirm, Radio, Row, Select, Space, Spin, Table, Tabs, Tag, Typography, message, notification } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import ReactECharts from 'echarts-for-react';
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api, formatNumber, formatTime } from '../api/client';
import PageHeader from '../components/PageHeader';
import PaperAdmin from './PaperAdmin';
import PriceText from '../components/PriceText';
import SignalTag from '../components/SignalTag';
import StockLink from '../components/StockLink';
import { backendEventTouchesAnyStock, buildStockSearchOptions, canApplyPaperIntradayResult, createPaperTradeMarkers, isReasonablePaperPhone, normalizePaperPhone, PAPER_INTRADAY_POLL_INTERVAL_MS, paperIntradayRefreshCode, paperIntradayRefreshPlan, selectLatestTradingDayIntraday, shouldRefreshPaperIntraday, stockCodeFromBackendEvent, upsertPaperWatchItem } from '../features/paper-trading/paperTradingData';
import type { PaperIntradayRefreshMode } from '../features/paper-trading/paperTradingData';
import { createIntradayKlineOption } from '../features/stock-detail/charts/stockCharts';
import { useBackendEvents } from '../hooks/useBackendEvents';
import { useThemeMode } from '../theme/ThemeModeContext';
import type { IntradayKline, PaperAccount, PaperAccountCaptcha, PaperCashFlow, PaperEquityPoint, PaperOrder, PaperPerformanceCalendarDay, PaperPerformanceSummary, PaperPosition, PaperQuote, PaperStockPerformance, PaperSummary, PaperTrade, PaperWatchItem } from '../types';

const PAPER_TOKEN_KEY = 'market-agent.paper-trading.token';
const PAPER_ADMIN_TOKEN_KEY = 'market-agent.paper-admin.token';

type AuthTabKey = 'login' | 'create' | 'admin';
type AccountFormValues = { owner_name: string; password: string };
type CreateAccountFormValues = AccountFormValues & { phone: string; captcha_code: string };
type AdminLoginValues = { username: string; password: string };
type OrderFormValues = { code: string; side: 'buy' | 'sell'; order_type: string; quantity: number; limit_price?: number | null; trigger_price?: number | null };
type OrderFilterValues = { code?: string; side?: 'buy' | 'sell'; order_type?: PaperOrder['order_type']; status?: string };
type CashFlowFilterValues = { flow_type?: string; date_from?: string; date_to?: string };
type IntradayStatus = 'idle' | 'reading' | 'refreshing' | 'error';

const orderStatusColor: Record<string, string> = {
  filled: 'green',
  pending: 'blue',
  monitoring: 'gold',
  cancelled: 'default',
  rejected: 'red',
  triggered: 'purple',
};

const flowLabels: Record<string, string> = {
  buy_cost: '买入扣款',
  sell_income: '卖出入账',
  fee: '手续费',
  reset: '账户重置',
  freeze: '冻结资金',
  unfreeze: '释放冻结',
};

const HIGH_RISK_BUY_SIGNALS = new Set(['回避', '减仓']);
const POSITIVE_SELL_SIGNALS = new Set(['重点关注', '谨慎买入']);
const COMMISSION_RATE = 0.00025;
const TRANSFER_FEE_RATE = 0.00001;
const STAMP_TAX_RATE = 0.001;
const STOCK_SEARCH_DEBOUNCE_MS = 300;

function roundMoney(value: number): number {
  return Math.round(value * 100) / 100;
}

function formatShareCount(value?: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-';
  const abs = Math.abs(value);
  const formatUnit = (scaled: number, unit: string) => {
    const scaledAbs = Math.abs(scaled);
    const digits = scaledAbs >= 100 ? 0 : scaledAbs >= 10 ? 1 : 2;
    return `${scaled.toLocaleString('en-US', { maximumFractionDigits: digits })}${unit}`;
  };
  if (abs >= 1_000_000) return formatUnit(value / 1_000_000, 'm');
  if (abs >= 1_000) return formatUnit(value / 1_000, 'k');
  return formatNumber(value, 0);
}

export default function PaperTrading() {
  const [searchParams] = useSearchParams();
  const [token, setToken] = useState(() => localStorage.getItem(PAPER_TOKEN_KEY) ?? '');
  const [adminToken, setAdminToken] = useState(() => localStorage.getItem(PAPER_ADMIN_TOKEN_KEY) ?? '');
  const [authTab, setAuthTab] = useState<AuthTabKey>('login');
  const [registeredAccounts, setRegisteredAccounts] = useState<PaperAccount[]>([]);
  const [accountsLoading, setAccountsLoading] = useState(false);
  const [loading, setLoading] = useState(Boolean(token));
  const [submitting, setSubmitting] = useState(false);
  const [matching, setMatching] = useState(false);
  const [summary, setSummary] = useState<PaperSummary | null>(null);
  const [performance, setPerformance] = useState<PaperPerformanceSummary | null>(null);
  const [equity, setEquity] = useState<PaperEquityPoint[]>([]);
  const [quote, setQuote] = useState<PaperQuote | null>(null);
  const [paperWatchlist, setPaperWatchlist] = useState<PaperWatchItem[]>([]);
  const [selectedWatchCode, setSelectedWatchCode] = useState('');
  const [intraday, setIntraday] = useState<IntradayKline[]>([]);
  const [intradayLoading, setIntradayLoading] = useState(false);
  const [intradayStatus, setIntradayStatus] = useState<IntradayStatus>('idle');
  const [createCaptcha, setCreateCaptcha] = useState<PaperAccountCaptcha | null>(null);
  const [captchaSubmitting, setCaptchaSubmitting] = useState(false);
  const selectedWatchCodeRef = useRef('');
  const latestIntradayRequestIdRef = useRef(0);
  const [watchSubmitting, setWatchSubmitting] = useState(false);
  const [stockSearchKeyword, setStockSearchKeyword] = useState('');
  const [stockSearchOptions, setStockSearchOptions] = useState(() => buildStockSearchOptions([]));
  const [stockSearching, setStockSearching] = useState(false);
  const [stockPerformance, setStockPerformance] = useState<PaperStockPerformance[]>([]);
  const [calendarDays, setCalendarDays] = useState<PaperPerformanceCalendarDay[]>([]);
  const [orderFilters, setOrderFilters] = useState<OrderFilterValues>({});
  const [cashFlowFilters, setCashFlowFilters] = useState<CashFlowFilterValues>({});
  const [positions, setPositions] = useState<PaperPosition[]>([]);
  const [orders, setOrders] = useState<PaperOrder[]>([]);
  const [trades, setTrades] = useState<PaperTrade[]>([]);
  const [flows, setFlows] = useState<PaperCashFlow[]>([]);
  const [loginForm] = Form.useForm<AccountFormValues>();
  const [createForm] = Form.useForm<CreateAccountFormValues>();
  const [adminLoginForm] = Form.useForm<AdminLoginValues>();
  const [orderForm] = Form.useForm<OrderFormValues>();
  const [orderFilterForm] = Form.useForm<OrderFilterValues>();
  const [cashFlowFilterForm] = Form.useForm<CashFlowFilterValues>();
  const orderType = Form.useWatch('order_type', orderForm);
  const orderCode = Form.useWatch('code', orderForm);
  const orderSide = Form.useWatch('side', orderForm);
  const orderQuantity = Form.useWatch('quantity', orderForm);
  const orderLimitPrice = Form.useWatch('limit_price', orderForm);
  const orderTriggerPrice = Form.useWatch('trigger_price', orderForm);
  const queryCode = searchParams.get('code')?.toUpperCase();
  const normalizedOrderCode = useMemo(() => String(orderCode ?? '').trim().toUpperCase(), [orderCode]);
  const { mode: themeMode } = useThemeMode();

  const stockAutoCompleteOptions = useMemo(() => stockSearchOptions.map((option) => ({
    value: option.value,
    label: (
      <div className="paper-stock-option">
        <strong>{option.name}</strong>
        <span>{option.code}{option.industry ? ` · ${option.industry}` : ''}</span>
      </div>
    ),
  })), [stockSearchOptions]);

  const loadRegisteredAccounts = useCallback(async () => {
    setAccountsLoading(true);
    try {
      const result = await api.paperAccounts();
      setRegisteredAccounts(result.items);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载模拟账户列表失败');
      setRegisteredAccounts([]);
    } finally {
      setAccountsLoading(false);
    }
  }, []);

  const load = useCallback(async (activeToken = token, showSpinner = false) => {
    if (!activeToken) return;
    if (showSpinner) setLoading(true);
    try {
      const [summaryRes, performanceRes, equityRes, watchlistRes, stockPerformanceRes, calendarRes, positionsRes, ordersRes, tradesRes, flowsRes] = await Promise.all([
        api.paperSummary(activeToken),
        api.paperPerformanceSummary(activeToken),
        api.paperEquity(activeToken),
        api.paperWatchlist(activeToken),
        api.paperPerformanceByStock(activeToken),
        api.paperPerformanceCalendar(activeToken),
        api.paperPositions(activeToken),
        api.paperOrders(activeToken, orderFilters),
        api.paperTrades(activeToken),
        api.paperCashFlows(activeToken, cashFlowFilters),
      ]);
      setSummary(summaryRes);
      setPerformance(performanceRes);
      setEquity(equityRes.items);
      setPaperWatchlist(watchlistRes.items);
      setStockPerformance(stockPerformanceRes.items);
      setCalendarDays(calendarRes.items);
      setPositions(positionsRes.items);
      setOrders(ordersRes.items);
      setTrades(tradesRes.items);
      setFlows(flowsRes.items);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载模拟交易账户失败');
      localStorage.removeItem(PAPER_TOKEN_KEY);
      setToken('');
      setSummary(null);
      setPerformance(null);
      setEquity([]);
      setPaperWatchlist([]);
      setSelectedWatchCode('');
      setIntraday([]);
      setIntradayStatus('idle');
      setIntradayLoading(false);
      setStockPerformance([]);
      setCalendarDays([]);
    } finally {
      if (showSpinner) setLoading(false);
      else setLoading(false);
    }
  }, [cashFlowFilters, orderFilters, token]);

  useEffect(() => {
    if (token && !adminToken) void load(token, true);
  }, [adminToken, load, token]);

  useEffect(() => {
    if (!token && !adminToken) void loadRegisteredAccounts();
  }, [adminToken, loadRegisteredAccounts, token]);

  useEffect(() => {
    if (queryCode) orderForm.setFieldsValue({ code: queryCode, side: 'buy', order_type: 'market', quantity: 100 });
  }, [orderForm, queryCode]);

  useEffect(() => {
    const keyword = stockSearchKeyword.trim();
    if (!keyword) {
      setStockSearchOptions([]);
      setStockSearching(false);
      return undefined;
    }
    const timer = window.setTimeout(async () => {
      setStockSearching(true);
      try {
        const result = await api.stocks(keyword, 'stock');
        setStockSearchOptions(buildStockSearchOptions(result.items));
      } catch {
        setStockSearchOptions([]);
      } finally {
        setStockSearching(false);
      }
    }, STOCK_SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [stockSearchKeyword]);

  useEffect(() => {
    const code = normalizedOrderCode;
    if (!token || !code || code.length < 6) {
      setQuote(null);
      return undefined;
    }
    const timer = window.setTimeout(async () => {
      try {
        setQuote(await api.paperQuote(token, code));
      } catch {
        setQuote(null);
      }
    }, 300);
    return () => window.clearTimeout(timer);
  }, [normalizedOrderCode, token]);

  const paperWatchCodes = useMemo(() => new Set(paperWatchlist.map((item) => item.stock.code)), [paperWatchlist]);

  useEffect(() => {
    if (selectedWatchCode && paperWatchCodes.has(selectedWatchCode)) return;
    const preferredCode = queryCode && paperWatchCodes.has(queryCode) ? queryCode : paperWatchlist[0]?.stock.code ?? '';
    setSelectedWatchCode(preferredCode);
    if (preferredCode && !normalizedOrderCode) orderForm.setFieldsValue({ code: preferredCode });
  }, [normalizedOrderCode, orderForm, paperWatchCodes, paperWatchlist, queryCode, selectedWatchCode]);

  const selectedWatchItem = useMemo(
    () => paperWatchlist.find((item) => item.stock.code === selectedWatchCode) ?? null,
    [paperWatchlist, selectedWatchCode],
  );
  const selectedWatchCodeForChart = selectedWatchItem?.stock.code ?? '';
  const latestIntraday = useMemo(() => selectLatestTradingDayIntraday(intraday), [intraday]);
  const latestIntradayTime = latestIntraday.at(-1)?.bar_time;
  const intradayTradeMarkers = useMemo(
    () => createPaperTradeMarkers(latestIntraday, trades, selectedWatchCodeForChart),
    [latestIntraday, selectedWatchCodeForChart, trades],
  );
  const intradayStatusText = intradayStatus === 'refreshing'
    ? '分钟 K 后台更新中'
    : intradayStatus === 'reading'
      ? '读取本地分钟 K'
      : intradayStatus === 'error'
        ? '分钟 K 更新失败'
        : latestIntradayTime
          ? `分钟 K ${formatTime(latestIntradayTime)}`
          : '暂无分钟 K';
  const intradayOption = useMemo(() => createIntradayKlineOption(latestIntraday, themeMode, intradayTradeMarkers), [intradayTradeMarkers, latestIntraday, themeMode]);
  const watchActiveKey = paperWatchlist.length ? selectedWatchCodeForChart || paperWatchlist[0].stock.code : 'empty';
  const canAddCurrentWatch = normalizedOrderCode.length >= 6 && !paperWatchCodes.has(normalizedOrderCode);

  const loadIntraday = useCallback(async (code: string, options: { mode?: PaperIntradayRefreshMode; notify?: boolean } = {}) => {
    const normalizedCode = code.trim().toUpperCase();
    if (!normalizedCode) return;
    const mode = options.mode ?? 'event';
    const plan = paperIntradayRefreshPlan(mode);
    const requestId = ++latestIntradayRequestIdRef.current;
    setIntradayLoading(true);
    setIntradayStatus(plan.readCacheFirst ? 'reading' : 'refreshing');

    const canApplyResult = () => canApplyPaperIntradayResult(
      requestId,
      latestIntradayRequestIdRef.current,
      selectedWatchCodeRef.current,
      normalizedCode,
    );

    const readCachedIntraday = async () => {
      const result = await api.intraday(normalizedCode, 1, 1);
      if (!canApplyResult()) return false;
      setIntraday(selectLatestTradingDayIntraday(result.items));
      return true;
    };

    const finishRequest = (status: IntradayStatus = 'idle') => {
      if (!canApplyResult()) return;
      setIntradayStatus(status);
      setIntradayLoading(false);
    };

    const refreshSource = async () => {
      if (canApplyResult()) setIntradayStatus('refreshing');
      try {
        await api.collectStockIntraday(normalizedCode, 1, 1);
        await readCachedIntraday();
        if (canApplyResult() && options.notify) message.success('分钟 K 已更新');
        finishRequest('idle');
      } catch (error) {
        if (!canApplyResult()) return;
        if (plan.clearOnError) setIntraday([]);
        setIntradayStatus('error');
        setIntradayLoading(false);
        if (options.notify) message.error(error instanceof Error ? error.message : '分钟 K 更新失败');
      }
    };

    try {
      if (plan.readCacheFirst) {
        try {
          await readCachedIntraday();
        } catch (error) {
          if (!plan.refreshSourceInBackground) throw error;
        }
      }
      if (plan.refreshSourceInBackground) {
        void refreshSource();
        return;
      }
      if (options.notify) message.success('分钟 K 已更新');
      finishRequest('idle');
    } catch (error) {
      if (!canApplyResult()) return;
      if (plan.clearOnError) setIntraday([]);
      setIntradayStatus('error');
      setIntradayLoading(false);
      if (options.notify) message.error(error instanceof Error ? error.message : '分钟 K 更新失败');
    }
  }, []);

  useEffect(() => {
    selectedWatchCodeRef.current = selectedWatchCodeForChart;
    latestIntradayRequestIdRef.current += 1;
  }, [selectedWatchCodeForChart]);

  useEffect(() => {
    if (!selectedWatchCodeForChart) {
      setIntraday([]);
      setIntradayStatus('idle');
      setIntradayLoading(false);
      return;
    }
    void loadIntraday(selectedWatchCodeForChart, { mode: 'switch' });
  }, [loadIntraday, selectedWatchCodeForChart]);

  useEffect(() => {
    if (!selectedWatchCodeForChart) return undefined;
    const timer = window.setInterval(() => {
      void loadIntraday(selectedWatchCodeForChart, { mode: 'poll' });
    }, PAPER_INTRADAY_POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [loadIntraday, selectedWatchCodeForChart]);

  useBackendEvents(['paper_trade.filled', 'paper_order.updated', 'paper_account.reset', 'paper_watchlist.updated', 'watchlist.updated', 'intraday.updated'], (event) => {
    if (!token || adminToken) return;
    const eventCode = stockCodeFromBackendEvent(event);
    if ((event.type === 'watchlist.updated' || event.type === 'intraday.updated') && eventCode && !paperWatchCodes.has(eventCode)) return;
    if ((event.type === 'watchlist.updated' || event.type === 'intraday.updated') && !backendEventTouchesAnyStock(event, paperWatchCodes)) return;
    void load(token, false);
    if (!shouldRefreshPaperIntraday(event)) return;
    const code = paperIntradayRefreshCode(event, selectedWatchCodeForChart);
    if (code) void loadIntraday(code);
  });

  const login = async (values: AccountFormValues) => {
    setSubmitting(true);
    try {
      const result = await api.loginPaperAccount(values);
      localStorage.removeItem(PAPER_ADMIN_TOKEN_KEY);
      localStorage.setItem(PAPER_TOKEN_KEY, result.token);
      setAdminToken('');
      setToken(result.token);
      message.success('已登录模拟交易账户');
      await load(result.token, true);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '登录失败');
    } finally {
      setSubmitting(false);
    }
  };

  const showCreateCaptcha = async () => {
    const phone = normalizePaperPhone(createForm.getFieldValue('phone'));
    if (!isReasonablePaperPhone(phone)) {
      message.error('请输入正确的手机号');
      return;
    }
    setCaptchaSubmitting(true);
    try {
      const captcha = await api.createPaperAccountCaptcha({ phone });
      setCreateCaptcha(captcha);
      createForm.setFieldsValue({ phone: captcha.phone, captcha_code: '' });
      notification.info({
        message: '模拟验证码',
        description: `手机号 ${captcha.phone} 的验证码：${captcha.captcha_code}`,
        duration: 8,
      });
    } catch (error) {
      setCreateCaptcha(null);
      message.error(error instanceof Error ? error.message : '获取验证码失败');
    } finally {
      setCaptchaSubmitting(false);
    }
  };

  const createAccount = async (values: CreateAccountFormValues) => {
    const phone = normalizePaperPhone(values.phone);
    if (!isReasonablePaperPhone(phone)) {
      message.error('请输入正确的手机号');
      return;
    }
    if (!createCaptcha || createCaptcha.phone !== phone) {
      message.error('请先获取当前手机号的验证码');
      return;
    }
    const captchaCode = values.captcha_code?.trim();
    if (!captchaCode) {
      message.error('请输入验证码');
      return;
    }
    setSubmitting(true);
    try {
      const accountPayload = {
        owner_name: values.owner_name,
        password: values.password,
        phone,
        captcha_id: createCaptcha.captcha_id,
        captcha_code: captchaCode,
      };
      await api.createPaperAccount(accountPayload);
      await loadRegisteredAccounts();
      const result = await api.loginPaperAccount({ owner_name: values.owner_name, password: values.password });
      localStorage.removeItem(PAPER_ADMIN_TOKEN_KEY);
      localStorage.setItem(PAPER_TOKEN_KEY, result.token);
      setAdminToken('');
      setToken(result.token);
      setCreateCaptcha(null);
      createForm.resetFields();
      message.success('模拟账户已创建');
      await load(result.token, true);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '创建账户失败');
    } finally {
      setSubmitting(false);
    }
  };

  const clearSession = () => {
    localStorage.removeItem(PAPER_TOKEN_KEY);
    setToken('');
    setSummary(null);
    setPerformance(null);
    setEquity([]);
    setQuote(null);
    setPaperWatchlist([]);
    setSelectedWatchCode('');
    setIntraday([]);
    setIntradayStatus('idle');
    setIntradayLoading(false);
    setCreateCaptcha(null);
    createForm.resetFields();
    setStockPerformance([]);
    setCalendarDays([]);
    setPositions([]);
    setOrders([]);
    setTrades([]);
    setFlows([]);
  };

  const loginAdmin = async (values: AdminLoginValues) => {
    setSubmitting(true);
    try {
      const result = await api.loginPaperAdmin(values);
      localStorage.removeItem(PAPER_TOKEN_KEY);
      localStorage.setItem(PAPER_ADMIN_TOKEN_KEY, result.token);
      clearSession();
      setAdminToken(result.token);
      message.success('管理员已登录');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '管理员登录失败');
    } finally {
      setSubmitting(false);
    }
  };

  const selectRegisteredAccount = (ownerName: string) => {
    loginForm.setFieldsValue({ owner_name: ownerName });
    setAuthTab('login');
  };

  const logout = async () => {
    const activeToken = token;
    if (!activeToken) {
      clearSession();
      return;
    }
    setSubmitting(true);
    try {
      await api.logoutPaperAccount(activeToken);
      message.success('已退出模拟交易账户');
    } catch {
      message.info('本地登录状态已清除');
    } finally {
      clearSession();
      setSubmitting(false);
    }
  };

  const resetAccount = async () => {
    if (!token) return;
    setSubmitting(true);
    try {
      const result = await api.resetPaperAccount(token);
      setSummary(result);
      await load(token, false);
      message.success('模拟账户已重置');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '重置失败');
    } finally {
      setSubmitting(false);
    }
  };

  const selectWatchStock = (code: string) => {
    selectedWatchCodeRef.current = code;
    latestIntradayRequestIdRef.current += 1;
    setSelectedWatchCode(code);
    orderForm.setFieldsValue({ code });
  };

  const addCurrentToWatchlist = async () => {
    if (!token) return;
    if (!normalizedOrderCode || normalizedOrderCode.length < 6) {
      message.warning('请先输入股票代码');
      return;
    }
    setWatchSubmitting(true);
    try {
      const result = await api.addPaperWatch(token, normalizedOrderCode);
      setPaperWatchlist((current) => upsertPaperWatchItem(current, result.item));
      selectWatchStock(result.item.stock.code);
      await load(token, false);
      void loadIntraday(result.item.stock.code, { mode: 'switch' });
      message.success(result.status === 'exists' ? '该股票已在账户自选股中' : '已加入账户自选股');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加入账户自选股失败');
    } finally {
      setWatchSubmitting(false);
    }
  };

  const removeFromWatchlist = async (code: string) => {
    if (!token) return;
    setWatchSubmitting(true);
    try {
      await api.removePaperWatch(token, code);
      await load(token, false);
      message.success('已移出账户自选股');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '移出账户自选股失败');
    } finally {
      setWatchSubmitting(false);
    }
  };

  const submitOrderDirect = async (values: OrderFormValues) => {
    if (!token) return;
    setSubmitting(true);
    try {
      await api.createPaperOrder(token, {
        code: values.code.trim().toUpperCase(),
        side: values.side,
        order_type: values.order_type,
        quantity: values.quantity,
        limit_price: values.order_type === 'limit' ? values.limit_price : null,
        trigger_price: values.order_type === 'take_profit' || values.order_type === 'stop_loss' ? values.trigger_price : null,
      });
      message.success(values.order_type === 'market' ? '市价委托已成交' : '委托已提交');
      await load(token, false);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '下单失败');
    } finally {
      setSubmitting(false);
    }
  };

  const submitOrder = async (values: OrderFormValues) => {
    const signal = quote?.strategy_signal;
    if (values.side === 'buy' && signal && HIGH_RISK_BUY_SIGNALS.has(signal)) {
      Modal.confirm({
        title: '当前策略信号偏谨慎',
        content: `最新策略为“${signal}”，买入前请确认仍要提交该委托。`,
        okText: '继续提交',
        cancelText: '返回修改',
        onOk: () => submitOrderDirect(values),
      });
      return;
    }
    if (values.side === 'sell' && signal && POSITIVE_SELL_SIGNALS.has(signal)) {
      Modal.confirm({
        title: '当前策略信号偏积极',
        content: `最新策略为“${signal}”，卖出可能与策略倾向相反，请确认是否继续。`,
        okText: '继续提交',
        cancelText: '返回修改',
        onOk: () => submitOrderDirect(values),
      });
      return;
    }
    await submitOrderDirect(values);
  };

  const cancelOrder = async (orderId: number) => {
    if (!token) return;
    setSubmitting(true);
    try {
      await api.cancelPaperOrder(token, orderId);
      message.success('委托已撤销');
      await load(token, false);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '撤单失败');
    } finally {
      setSubmitting(false);
    }
  };

  const runMatching = async () => {
    if (!token) return;
    setMatching(true);
    try {
      const result = await api.runPaperMatching(token);
      message.success(`撮合完成：检查 ${result.checked} 笔，触发 ${result.triggered} 笔，成交 ${result.filled} 笔`);
      await load(token, false);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '撮合失败');
    } finally {
      setMatching(false);
    }
  };

  const applyOrderFilters = (values: OrderFilterValues) => {
    setOrderFilters({
      code: values.code?.trim().toUpperCase() || undefined,
      side: values.side,
      order_type: values.order_type,
      status: values.status,
    });
  };

  const resetOrderFilters = () => {
    orderFilterForm.resetFields();
    setOrderFilters({});
  };

  const applyCashFlowFilters = (values: CashFlowFilterValues) => {
    setCashFlowFilters({
      flow_type: values.flow_type,
      date_from: values.date_from?.trim() || undefined,
      date_to: values.date_to?.trim() || undefined,
    });
  };

  const resetCashFlowFilters = () => {
    cashFlowFilterForm.resetFields();
    setCashFlowFilters({});
  };

  const orderEstimate = useMemo(() => {
    const quantity = Number(orderQuantity ?? 0);
    const fallbackPrice = quote?.price ?? 0;
    const price = orderType === 'limit'
      ? Number(orderLimitPrice || fallbackPrice)
      : orderType === 'take_profit' || orderType === 'stop_loss'
        ? fallbackPrice
        : fallbackPrice;
    if (!quantity || !price) return null;
    const amount = roundMoney(price * quantity);
    const commission = roundMoney(amount * COMMISSION_RATE);
    const transferFee = roundMoney(amount * TRANSFER_FEE_RATE);
    const stampTax = orderSide === 'sell' ? roundMoney(amount * STAMP_TAX_RATE) : 0;
    const feeTotal = roundMoney(commission + transferFee + stampTax);
    const cashAfter = orderSide === 'sell'
      ? (summary?.cash_available ?? 0) + amount - feeTotal
      : (summary?.cash_available ?? 0) - amount - feeTotal;
    return { price, quantity, amount, commission, transferFee, stampTax, feeTotal, cashAfter: roundMoney(cashAfter) };
  }, [orderLimitPrice, orderQuantity, orderSide, orderType, quote?.price, summary?.cash_available]);

  const equityOption = useMemo(() => ({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { top: 0, textStyle: { color: themeMode === 'dark' ? '#cbd5e1' : '#334155' } },
    grid: { top: 42, left: 46, right: 24, bottom: 36 },
    xAxis: {
      type: 'category',
      data: equity.map((item) => formatTime(item.snapshot_time)),
      axisLabel: { color: themeMode === 'dark' ? '#94a3b8' : '#64748b' },
    },
    yAxis: {
      type: 'value',
      min: (value: { min: number }) => Math.max(0, value.min - 0.01),
      axisLabel: { color: themeMode === 'dark' ? '#94a3b8' : '#64748b' },
      splitLine: { lineStyle: { color: themeMode === 'dark' ? '#1f2937' : '#e5e7eb' } },
    },
    series: [
      { name: '账户净值', type: 'line', smooth: true, showSymbol: false, data: equity.map((item) => item.net_value), lineStyle: { width: 2, color: '#2563eb' }, areaStyle: { opacity: 0.08 } },
      { name: '沪深300', type: 'line', smooth: true, showSymbol: false, data: equity.map((item) => item.benchmark_value), lineStyle: { width: 2, color: '#f59e0b' } },
    ],
  }), [equity, themeMode]);

  const holdingsOption = useMemo(() => ({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item', formatter: '{b}: {d}%' },
    series: [{
      type: 'pie',
      radius: ['45%', '72%'],
      avoidLabelOverlap: true,
      label: { formatter: '{b}\n{d}%', color: themeMode === 'dark' ? '#cbd5e1' : '#334155' },
      data: positions.map((position) => ({ name: position.name, value: position.market_value })),
    }],
  }), [positions, themeMode]);

  const positionTotals = useMemo(() => ({
    available: positions.reduce((sum, position) => sum + position.available_quantity, 0),
    total: positions.reduce((sum, position) => sum + position.total_quantity, 0),
  }), [positions]);

  const positionCardTitle = (
    <Space className="paper-position-title" size={8} wrap>
      <span>可交易持仓 / 持仓</span>
      <Typography.Text type="secondary" className="paper-position-title-count">
        {formatShareCount(positionTotals.available)} / {formatShareCount(positionTotals.total)}
      </Typography.Text>
    </Space>
  );

  const positionColumns: ColumnsType<PaperPosition> = useMemo(() => [
    { title: '股票', width: 150, render: (_: unknown, row) => <StockLink code={row.code} name={row.name} /> },
    {
      title: '可交易/持仓',
      width: 130,
      align: 'right',
      render: (_: unknown, row) => (
        <span className="paper-position-quantity">
          <Typography.Text strong>{formatShareCount(row.available_quantity)} / {formatShareCount(row.total_quantity)}</Typography.Text>
        </span>
      ),
    },
    { title: '冻结', dataIndex: 'frozen_quantity', width: 90, align: 'right' },
    { title: '成本', width: 90, align: 'right', render: (_: unknown, row) => formatNumber(row.avg_cost, 4) },
    { title: '现价', width: 90, align: 'right', render: (_: unknown, row) => formatNumber(row.market_price, 2) },
    { title: '市值', width: 110, align: 'right', render: (_: unknown, row) => formatNumber(row.market_value, 2) },
    { title: '浮盈亏', width: 110, align: 'right', render: (_: unknown, row) => <PriceText value={row.floating_pnl} /> },
    { title: '收益率', width: 100, align: 'right', render: (_: unknown, row) => <PriceText value={row.floating_pnl_pct} suffix="%" /> },
    { title: '占比', width: 90, align: 'right', render: (_: unknown, row) => `${formatNumber(row.asset_ratio_pct, 2)}%` },
    { title: '策略', width: 100, render: (_: unknown, row) => <SignalTag signal={row.strategy_signal ?? undefined} /> },
  ], []);

  const stockPerformanceColumns: ColumnsType<PaperStockPerformance> = useMemo(() => [
    { title: '股票', width: 150, render: (_: unknown, row) => <StockLink code={row.code} name={row.name} /> },
    { title: '持仓', dataIndex: 'current_quantity', width: 80, align: 'right' },
    { title: '买入量', dataIndex: 'buy_quantity', width: 90, align: 'right' },
    { title: '卖出量', dataIndex: 'sell_quantity', width: 90, align: 'right' },
    { title: '买入金额', width: 110, align: 'right', render: (_: unknown, row) => formatNumber(row.buy_amount, 2) },
    { title: '卖出金额', width: 110, align: 'right', render: (_: unknown, row) => formatNumber(row.sell_amount, 2) },
    { title: '费用', width: 90, align: 'right', render: (_: unknown, row) => formatNumber(row.fee_total, 2) },
    { title: '已实现', width: 110, align: 'right', render: (_: unknown, row) => <PriceText value={row.realized_pnl} /> },
    { title: '浮动', width: 110, align: 'right', render: (_: unknown, row) => <PriceText value={row.floating_pnl} /> },
    { title: '合计盈亏', width: 110, align: 'right', render: (_: unknown, row) => <PriceText value={row.total_pnl} /> },
  ], []);

  const calendarColumns: ColumnsType<PaperPerformanceCalendarDay> = useMemo(() => [
    { title: '日期', dataIndex: 'trade_date', width: 120 },
    { title: '当日 P&L', width: 120, align: 'right', render: (_: unknown, row) => <PriceText value={row.realized_pnl} /> },
    { title: '买入金额', width: 120, align: 'right', render: (_: unknown, row) => formatNumber(row.buy_amount, 2) },
    { title: '卖出金额', width: 120, align: 'right', render: (_: unknown, row) => formatNumber(row.sell_amount, 2) },
    { title: '费用', width: 90, align: 'right', render: (_: unknown, row) => formatNumber(row.fee_total, 2) },
    { title: '成交', dataIndex: 'trade_count', width: 80, align: 'right' },
    { title: '委托', dataIndex: 'order_count', width: 80, align: 'right' },
    { title: '流水', dataIndex: 'cash_flow_count', width: 80, align: 'right' },
  ], []);

  const orderColumns: ColumnsType<PaperOrder> = useMemo(() => [
    { title: '股票', width: 150, render: (_: unknown, row) => <StockLink code={row.code} name={row.name} /> },
    { title: '方向', width: 70, render: (_: unknown, row) => <Tag color={row.side === 'buy' ? 'red' : 'green'}>{row.side === 'buy' ? '买入' : '卖出'}</Tag> },
    { title: '类型', width: 80, render: (_: unknown, row) => orderTypeLabel(row.order_type) },
    { title: '状态', width: 90, render: (_: unknown, row) => <Tag color={orderStatusColor[row.status] ?? 'default'}>{row.status}</Tag> },
    { title: '数量', dataIndex: 'quantity', width: 90, align: 'right' },
    { title: '限价', width: 90, align: 'right', render: (_: unknown, row) => formatNumber(row.limit_price, 2) },
    { title: '触发价', width: 90, align: 'right', render: (_: unknown, row) => formatNumber(row.trigger_price, 2) },
    { title: '成交价', width: 90, align: 'right', render: (_: unknown, row) => formatNumber(row.avg_fill_price, 2) },
    { title: '冻结', width: 100, align: 'right', render: (_: unknown, row) => row.side === 'buy' ? formatNumber(row.frozen_cash, 2) : `${row.frozen_quantity}` },
    { title: '费用', width: 90, align: 'right', render: (_: unknown, row) => formatNumber(row.fee_total, 2) },
    { title: '时间', width: 170, render: (_: unknown, row) => formatTime(row.created_at) },
    {
      title: '操作',
      width: 80,
      fixed: 'right',
      render: (_: unknown, row) => (
        row.status === 'pending' || row.status === 'monitoring' ? (
          <Popconfirm title="撤销该委托？" okText="撤单" cancelText="取消" onConfirm={() => cancelOrder(row.id)}>
            <Button danger type="text" size="small" icon={<CloseCircleOutlined />} loading={submitting} />
          </Popconfirm>
        ) : null
      ),
    },
  ], [submitting, token]);

  const tradeColumns: ColumnsType<PaperTrade> = useMemo(() => [
    { title: '股票', width: 150, render: (_: unknown, row) => <StockLink code={row.code} name={row.name} /> },
    { title: '方向', width: 70, render: (_: unknown, row) => <Tag color={row.side === 'buy' ? 'red' : 'green'}>{row.side === 'buy' ? '买入' : '卖出'}</Tag> },
    { title: '数量', dataIndex: 'quantity', width: 90, align: 'right' },
    { title: '价格', width: 90, align: 'right', render: (_: unknown, row) => formatNumber(row.price, 2) },
    { title: '金额', width: 110, align: 'right', render: (_: unknown, row) => formatNumber(row.amount, 2) },
    { title: '费用', width: 90, align: 'right', render: (_: unknown, row) => formatNumber(row.fee_total, 2) },
    { title: '来源', dataIndex: 'price_source', width: 120 },
    { title: '时间', width: 170, render: (_: unknown, row) => formatTime(row.trade_time) },
  ], []);

  const flowColumns: ColumnsType<PaperCashFlow> = useMemo(() => [
    { title: '类型', width: 100, render: (_: unknown, row) => flowLabels[row.flow_type] ?? row.flow_type },
    { title: '金额', width: 110, align: 'right', render: (_: unknown, row) => <PriceText value={row.amount} /> },
    { title: '余额', width: 120, align: 'right', render: (_: unknown, row) => formatNumber(row.cash_balance_after, 2) },
    { title: '备注', dataIndex: 'remark', width: 160 },
    { title: '时间', width: 170, render: (_: unknown, row) => formatTime(row.created_at) },
  ], []);

  if (adminToken) return <PaperAdmin onSessionCleared={() => setAdminToken('')} />;

  if (loading && token && !summary) return <Spin fullscreen tip="加载模拟交易账户" />;

  if (!token || !summary) {
    return (
      <>
        <PageHeader title="Transaction" description="模拟交易账户与管理员视图统一入口" />
        <Row gutter={[18, 18]} className="paper-auth-grid">
          <Col xs={24} lg={8} className="paper-auth-intro-col">
            <Card className="paper-auth-intro" bordered={false}>
              <div className="paper-auth-mark"><WalletOutlined /></div>
              <Typography.Title level={3}>模拟交易账户</Typography.Title>
              <Typography.Paragraph>
                每个账户独立保存资金、持仓、自选股和交易记录，适合验证策略信号与下单流程。
              </Typography.Paragraph>
              <div className="paper-auth-points">
                <div className="paper-auth-point">
                  <LineChartOutlined />
                  <div>
                    <strong>行情驱动</strong>
                    <span>下单时读取最新行情快照并更新估值。</span>
                  </div>
                </div>
                <div className="paper-auth-point">
                  <SafetyCertificateOutlined />
                  <div>
                    <strong>账户隔离</strong>
                    <span>不同账户的持仓、自选股和流水互不混用。</span>
                  </div>
                </div>
              </div>
              <div className="paper-auth-facts">
                <div>
                  <span>默认初始资金</span>
                  <strong>500,000 元</strong>
                </div>
                <div>
                  <span>交易范围</span>
                  <strong>A 股代码</strong>
                </div>
              </div>
            </Card>
          </Col>
          <Col xs={24} lg={8} className="paper-auth-panel-col">
            <Card className="paper-auth-panel">
              <Tabs
                size="large"
                className="paper-auth-tabs"
                activeKey={authTab}
                onChange={(key) => {
                  setAuthTab(key as AuthTabKey);
                  if (key === 'create') {
                    createForm.resetFields();
                    setCreateCaptcha(null);
                  }
                }}
                items={[
                  {
                    key: 'login',
                    label: <span><LoginOutlined />登录账户</span>,
                    children: (
                      <Form form={loginForm} layout="vertical" onFinish={login}>
                        <Form.Item name="owner_name" label="账户名" rules={[{ required: true, message: '请输入账户名' }]}>
                          <Input autoComplete="username" size="large" />
                        </Form.Item>
                        <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }, { min: 6, message: '密码需至少 6 个字符' }]}>
                          <Input.Password autoComplete="current-password" size="large" />
                        </Form.Item>
                        <Form.Item className="paper-auth-submit">
                          <Button block type="primary" htmlType="submit" icon={<LoginOutlined />} loading={submitting} size="large">登录</Button>
                        </Form.Item>
                      </Form>
                    ),
                  },
                  {
                    key: 'create',
                    label: <span><UserAddOutlined />创建账户</span>,
                    children: (
                      <Form form={createForm} layout="vertical" initialValues={{ owner_name: '', phone: '', password: '', captcha_code: '' }} onFinish={createAccount}>
                        <Form.Item name="owner_name" label="账户名" rules={[{ required: true, message: '请输入账户名' }, { min: 2, message: '至少 2 个字符' }]}>
                          <Input autoComplete="off" size="large" />
                        </Form.Item>
                        <Form.Item
                          name="phone"
                          label="手机号"
                          rules={[
                            { required: true, message: '请输入手机号' },
                            {
                              validator: (_, value) => (
                                !value || isReasonablePaperPhone(value)
                                  ? Promise.resolve()
                                  : Promise.reject(new Error('请输入正确的手机号'))
                              ),
                            },
                          ]}
                        >
                          <Input
                            autoComplete="tel"
                            size="large"
                            onChange={() => {
                              setCreateCaptcha(null);
                              createForm.setFieldsValue({ captcha_code: '' });
                            }}
                          />
                        </Form.Item>
                        <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }, { min: 6, message: '密码需至少 6 个字符' }]}>
                          <Input.Password autoComplete="new-password" size="large" />
                        </Form.Item>
                        <Form.Item name="captcha_code" label="验证码" rules={[{ required: true, message: '请输入验证码' }]}>
                          <Space.Compact className="paper-captcha-input">
                            <Input autoComplete="off" size="large" />
                            <Button size="large" loading={captchaSubmitting} onClick={showCreateCaptcha}>获取验证码</Button>
                          </Space.Compact>
                        </Form.Item>
                        <Form.Item className="paper-auth-submit">
                          <Button block type="primary" htmlType="submit" icon={<UserAddOutlined />} loading={submitting} size="large">创建并登录</Button>
                        </Form.Item>
                      </Form>
                    ),
                  },
                  {
                    key: 'admin',
                    label: <span><AuditOutlined />管理员</span>,
                    children: (
                      <Form form={adminLoginForm} layout="vertical" initialValues={{ username: 'admin' }} onFinish={loginAdmin}>
                        <Form.Item name="username" label="管理员账号" rules={[{ required: true, message: '请输入管理员账号' }]}>
                          <Input autoComplete="username" size="large" />
                        </Form.Item>
                        <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入管理员密码' }, { min: 6, message: '密码需至少 6 个字符' }]}>
                          <Input.Password autoComplete="current-password" placeholder="admin..." size="large" />
                        </Form.Item>
                        <Form.Item className="paper-auth-submit">
                          <Button block type="primary" htmlType="submit" icon={<AuditOutlined />} loading={submitting} size="large">登录管理</Button>
                        </Form.Item>
                      </Form>
                    ),
                  },
                ]}
              />
            </Card>
          </Col>
          <Col xs={24} lg={8} className="paper-auth-accounts-col">
            <Card
              title="已注册账户"
              className="paper-auth-panel paper-account-picker-card"
              extra={<Button size="small" icon={<ReloadOutlined />} loading={accountsLoading} onClick={loadRegisteredAccounts}>刷新</Button>}
            >
              <Spin spinning={accountsLoading}>
                {registeredAccounts.length ? (
                  <div className="paper-account-picker-list">
                    {registeredAccounts.map((account) => (
                      <button
                        key={account.id}
                        type="button"
                        className="paper-account-picker-item"
                        onClick={() => selectRegisteredAccount(account.owner_name)}
                      >
                        <span>{account.owner_name}</span>
                        <small>ID {account.id}</small>
                      </button>
                    ))}
                  </div>
                ) : (
                  <Empty description="暂无注册账户" />
                )}
              </Spin>
            </Card>
          </Col>
        </Row>
      </>
    );
  }

  const accountOverviewCard = (
    <Card title="账户概览" className="paper-account-card">
      <div className="paper-stat-grid">
        <CompactStat label="总资产" value={`${formatNumber(summary.total_assets, 2)} 元`} />
        <CompactStat label="可用现金" value={`${formatNumber(summary.cash_available, 2)} 元`} />
        <CompactStat label="冻结资金" value={`${formatNumber(summary.cash_frozen, 2)} 元`} />
        <CompactStat label="持仓市值" value={`${formatNumber(summary.position_market_value, 2)} 元`} />
        <CompactStat label="持仓数" value={`${summary.position_count} 只`} />
        <CompactStat label="成交次数" value={`${summary.trade_count} 笔`} />
      </div>
      <Tabs
        size="small"
        className="paper-account-tabs"
        items={[
          {
            key: 'equity',
            label: '净值曲线',
            children: <ReactECharts option={equityOption} className="paper-overview-chart" />,
          },
          {
            key: 'holdings',
            label: '持仓占比',
            children: <ReactECharts option={holdingsOption} className="paper-overview-chart" />,
          },
          {
            key: 'performance',
            label: '绩效指标',
            children: (
              <div className="paper-stat-grid paper-performance-stats">
                <CompactStat label="已实现盈亏" value={<PriceText value={performance?.realized_pnl} />} extra={`总收益率 ${formatNumber(performance?.total_return_pct, 2)}%`} />
                <CompactStat label="胜率" value={`${formatNumber(performance?.win_rate_pct, 2)}%`} extra={`${performance?.winning_trades ?? 0}/${performance?.closed_trade_count ?? 0} 笔`} />
                <CompactStat label="平均盈亏" value={<PriceText value={performance?.average_pnl} />} extra={`盈利 ${formatNumber(performance?.average_profit, 2)} / 亏损 ${formatNumber(performance?.average_loss, 2)}`} />
                <CompactStat label="盈亏比" value={formatNumber(performance?.profit_loss_ratio, 2)} extra={`最大回撤 ${formatNumber(performance?.max_drawdown_pct, 2)}%`} />
                <CompactStat label="年化收益率" value={`${formatNumber(performance?.annualized_return_pct, 2)}%`} extra="按当前净值快照估算" />
                <CompactStat label="最大单笔盈利" value={<PriceText value={performance?.max_single_profit} />} extra={`最大亏损 ${formatNumber(performance?.max_single_loss, 2)}`} />
              </div>
            ),
          },
        ]}
      />
    </Card>
  );

  return (
    <>
      <PageHeader
        title="模拟交易"
        description={`${summary.account.owner_name} · 初始资金 ${formatNumber(summary.account.initial_cash, 0)} 元`}
        extra={(
          <Space wrap>
            <Button icon={<ReloadOutlined />} onClick={() => load(token, true)}>刷新</Button>
            <Button icon={<SyncOutlined />} loading={matching} onClick={runMatching}>运行撮合</Button>
            <Popconfirm title="重置模拟账户？" description="持仓、委托、成交和流水会被清空。" okText="重置" cancelText="取消" onConfirm={resetAccount}>
              <Button danger loading={submitting}>重置账户</Button>
            </Popconfirm>
            <Button onClick={logout} loading={submitting}>退出</Button>
          </Space>
        )}
      />

      <Row gutter={[16, 16]} className="section-gap paper-workbench">
        <Col xs={24} xl={8}>
          <Card
            title={<Space><ShoppingCartOutlined />下单面板</Space>}
            extra={<Button size="small" icon={<PlusOutlined />} loading={watchSubmitting} disabled={!canAddCurrentWatch} onClick={addCurrentToWatchlist}>加入自选</Button>}
            className="paper-order-card"
          >
            <Form
              form={orderForm}
              layout="vertical"
              initialValues={{ code: queryCode ?? '', side: 'buy', order_type: 'market', quantity: 100 }}
              onFinish={submitOrder}
            >
              <Form.Item name="code" label="股票代码" rules={[{ required: true, message: '请输入股票代码' }]}>
                <AutoComplete
                  allowClear
                  options={stockAutoCompleteOptions}
                  filterOption={false}
                  onSearch={setStockSearchKeyword}
                  onSelect={(value) => {
                    orderForm.setFieldsValue({ code: String(value).toUpperCase() });
                    setStockSearchKeyword('');
                  }}
                  onClear={() => {
                    setStockSearchKeyword('');
                    setStockSearchOptions([]);
                  }}
                  placeholder="输入代码或名称，例如 300308.SZ / 中际旭创"
                  notFoundContent={stockSearchKeyword.trim() ? (stockSearching ? '搜索中...' : '未找到匹配股票') : '输入代码或名称'}
                  className="paper-stock-search"
                />
              </Form.Item>
              <div className="paper-quote-panel">
                <div className="paper-quote-row">
                  <Typography.Text type="secondary">当前价</Typography.Text>
                  <Typography.Text strong>{quote ? `${formatNumber(quote.price, 2)} 元` : '-'}</Typography.Text>
                </div>
                <div className="paper-quote-row">
                  <Typography.Text type="secondary">价格来源</Typography.Text>
                  <Tag color={quote?.is_realtime ? 'green' : 'gold'}>{quote?.price_source ?? '-'}</Tag>
                </div>
                <div className="paper-quote-row">
                  <Typography.Text type="secondary">涨跌停</Typography.Text>
                  <Typography.Text>{quote?.limit_down !== null && quote?.limit_down !== undefined && quote?.limit_up !== null && quote?.limit_up !== undefined ? `${formatNumber(quote.limit_down, 2)} - ${formatNumber(quote.limit_up, 2)}` : '-'}</Typography.Text>
                </div>
                <div className="paper-quote-row">
                  <Typography.Text type="secondary">策略信号</Typography.Text>
                  <Space size={6}>
                    <SignalTag signal={quote?.strategy_signal ?? undefined} />
                    {quote?.strategy_confidence !== null && quote?.strategy_confidence !== undefined ? <Typography.Text type="secondary">{formatNumber(quote.strategy_confidence, 0)}%</Typography.Text> : null}
                  </Space>
                </div>
                <div className="paper-quote-row">
                  <Typography.Text type="secondary">预计金额</Typography.Text>
                  <Typography.Text>{orderEstimate ? `${formatNumber(orderEstimate.amount, 2)} 元` : '-'}</Typography.Text>
                </div>
                <div className="paper-quote-row">
                  <Typography.Text type="secondary">预计费用</Typography.Text>
                  <Typography.Text>{orderEstimate ? `${formatNumber(orderEstimate.feeTotal, 2)} 元` : '-'}</Typography.Text>
                </div>
                <div className="paper-quote-row">
                  <Typography.Text type="secondary">预计可用现金</Typography.Text>
                  <PriceText value={orderEstimate?.cashAfter} />
                </div>
              </div>
              <Form.Item name="side" label="方向">
                <Radio.Group optionType="button" buttonStyle="solid" options={[{ label: '买入', value: 'buy' }, { label: '卖出', value: 'sell' }]} />
              </Form.Item>
              <Form.Item name="order_type" label="订单类型">
                <Select options={[{ label: '市价单', value: 'market' }, { label: '限价单', value: 'limit' }, { label: '止盈单', value: 'take_profit' }, { label: '止损单', value: 'stop_loss' }]} />
              </Form.Item>
              {orderType === 'limit' ? (
                <Form.Item name="limit_price" label="限价" rules={[{ required: true, message: '请输入限价' }]}>
                  <InputNumber min={0.01} step={0.01} precision={2} className="paper-quantity-input" />
                </Form.Item>
              ) : null}
              {orderType === 'take_profit' || orderType === 'stop_loss' ? (
                <Form.Item name="trigger_price" label="触发价" rules={[{ required: true, message: '请输入触发价' }]}>
                  <InputNumber min={0.01} step={0.01} precision={2} className="paper-quantity-input" />
                </Form.Item>
              ) : null}
              <Form.Item name="quantity" label="数量" rules={[{ required: true, message: '请输入数量' }]}>
                <InputNumber min={100} step={100} precision={0} className="paper-quantity-input" />
              </Form.Item>
              <Button type="primary" htmlType="submit" loading={submitting} block>提交委托</Button>
            </Form>
            <Typography.Text className="muted paper-order-note">市价单立即按最新价成交；限价单未达价时冻结资金或可卖持仓；止盈/止损进入监控，运行撮合后按最新价触发。</Typography.Text>
          </Card>
        </Col>
        <Col xs={24} xl={16}>
          <Card
            title="账户自选股与分钟 K"
            extra={<Button size="small" icon={<ReloadOutlined />} loading={intradayLoading} disabled={!selectedWatchCodeForChart} onClick={() => loadIntraday(selectedWatchCodeForChart, { mode: 'manual', notify: true })}>更新分钟 K</Button>}
            className="paper-watch-card"
          >
            <Tabs
              activeKey={watchActiveKey}
              onChange={(key) => {
                if (key !== 'empty') selectWatchStock(key);
              }}
              items={paperWatchlist.length ? paperWatchlist.map((item) => ({
                key: item.stock.code,
                label: (
                  <span className="paper-watch-tab-label">
                    <strong>{item.stock.name}</strong>
                    <span>{item.stock.code}</span>
                  </span>
                ),
                children: (
                  <div className="paper-watch-panel">
                    <div className="paper-watch-header">
                      <div className="paper-watch-title">
                        <StockLink code={item.stock.code} name={item.stock.name} />
                        <Space size={8} wrap>
                          <Typography.Text className="muted">
                            最新价 {item.latest_snapshot?.price !== null && item.latest_snapshot?.price !== undefined ? `${formatNumber(item.latest_snapshot.price, 2)} 元` : '-'}
                          </Typography.Text>
                          <SignalTag signal={item.latest_advice?.signal ?? undefined} />
                          <Typography.Text className={`muted paper-intraday-status paper-intraday-status-${intradayStatus}`}>{intradayStatusText}</Typography.Text>
                        </Space>
                      </div>
                      <Space wrap>
                        <Button size="small" icon={<ShoppingCartOutlined />} onClick={() => selectWatchStock(item.stock.code)}>填入下单</Button>
                        <Popconfirm title="移出账户自选股？" okText="移出" cancelText="取消" onConfirm={() => removeFromWatchlist(item.stock.code)}>
                          <Button danger type="text" size="small" icon={<DeleteOutlined />} loading={watchSubmitting} />
                        </Popconfirm>
                      </Space>
                    </div>
                    <div className="paper-watch-chart-shell">
                      <ReactECharts option={intradayOption} className="paper-intraday-chart" style={{ height: '100%', width: '100%' }} />
                    </div>
                  </div>
                ),
              })) : [{
                key: 'empty',
                label: '自选股',
                children: (
                  <Empty description="当前账户还没有自选股">
                    <Button type="primary" icon={<PlusOutlined />} loading={watchSubmitting} disabled={!normalizedOrderCode} onClick={addCurrentToWatchlist}>加入当前代码</Button>
                  </Empty>
                ),
              }]}
            />
          </Card>
        </Col>
      </Row>

      <div className="section-gap">
        <Card title={positionCardTitle} className="paper-position-card">
          <Table<PaperPosition> rowKey="stock_id" size="small" columns={positionColumns} dataSource={positions} pagination={false} scroll={{ x: 900 }} />
        </Card>
      </div>

      <div className="section-gap">
        {accountOverviewCard}
      </div>

      <div className="section-gap">
        <Card title="记录中心" className="paper-records-card">
          <Tabs
            size="small"
            items={[
              {
                key: 'orders',
                label: '委托记录',
                children: (
                  <>
                    <Form form={orderFilterForm} layout="vertical" onFinish={applyOrderFilters} className="paper-filter-form">
                      <Row gutter={[12, 0]}>
                        <Col xs={24} sm={12} lg={6}>
                          <Form.Item name="code" label="股票代码">
                            <Input placeholder="300308.SZ" allowClear />
                          </Form.Item>
                        </Col>
                        <Col xs={24} sm={12} lg={6}>
                          <Form.Item name="side" label="方向">
                            <Select allowClear options={[{ label: '买入', value: 'buy' }, { label: '卖出', value: 'sell' }]} />
                          </Form.Item>
                        </Col>
                        <Col xs={24} sm={12} lg={6}>
                          <Form.Item name="order_type" label="类型">
                            <Select allowClear options={[{ label: '市价', value: 'market' }, { label: '限价', value: 'limit' }, { label: '止盈', value: 'take_profit' }, { label: '止损', value: 'stop_loss' }]} />
                          </Form.Item>
                        </Col>
                        <Col xs={24} sm={12} lg={6}>
                          <Form.Item name="status" label="状态">
                            <Select allowClear options={[{ label: '已成交', value: 'filled' }, { label: '待成交', value: 'pending' }, { label: '监控中', value: 'monitoring' }, { label: '已撤销', value: 'cancelled' }, { label: '已拒绝', value: 'rejected' }]} />
                          </Form.Item>
                        </Col>
                      </Row>
                      <Space className="paper-filter-actions">
                        <Button type="primary" htmlType="submit">筛选</Button>
                        <Button onClick={resetOrderFilters}>重置</Button>
                      </Space>
                    </Form>
                    <Table<PaperOrder> rowKey="id" size="small" columns={orderColumns} dataSource={orders} pagination={{ pageSize: 6 }} scroll={{ x: 1160 }} />
                  </>
                ),
              },
              {
                key: 'trades',
                label: '成交记录',
                children: <Table<PaperTrade> rowKey="id" size="small" columns={tradeColumns} dataSource={trades} pagination={{ pageSize: 6 }} scroll={{ x: 900 }} />,
              },
              {
                key: 'flows',
                label: '资金流水',
                children: (
                  <>
                    <Form form={cashFlowFilterForm} layout="vertical" onFinish={applyCashFlowFilters} className="paper-filter-form">
                      <Row gutter={[12, 0]}>
                        <Col xs={24} sm={12} lg={6}>
                          <Form.Item name="flow_type" label="流水类型">
                            <Select allowClear options={[
                              { label: '买入扣款', value: 'buy_cost' },
                              { label: '卖出入账', value: 'sell_income' },
                              { label: '手续费', value: 'fee' },
                              { label: '账户重置', value: 'reset' },
                            ]} />
                          </Form.Item>
                        </Col>
                        <Col xs={24} sm={12} lg={6}>
                          <Form.Item name="date_from" label="开始日期">
                            <Input placeholder="YYYY-MM-DD" allowClear />
                          </Form.Item>
                        </Col>
                        <Col xs={24} sm={12} lg={6}>
                          <Form.Item name="date_to" label="结束日期">
                            <Input placeholder="YYYY-MM-DD" allowClear />
                          </Form.Item>
                        </Col>
                      </Row>
                      <Space className="paper-filter-actions">
                        <Button type="primary" htmlType="submit">筛选</Button>
                        <Button onClick={resetCashFlowFilters}>重置</Button>
                      </Space>
                    </Form>
                    <Table<PaperCashFlow> rowKey="id" size="small" columns={flowColumns} dataSource={flows} pagination={{ pageSize: 8 }} scroll={{ x: 720 }} />
                  </>
                ),
              },
              {
                key: 'calendar',
                label: '交易日历',
                children: (
                  <Table<PaperPerformanceCalendarDay>
                    rowKey="trade_date"
                    size="small"
                    columns={calendarColumns}
                    dataSource={calendarDays}
                    pagination={{ pageSize: 6 }}
                    scroll={{ x: 830 }}
                    expandable={{ expandedRowRender: renderCalendarDetails }}
                  />
                ),
              },
              {
                key: 'stock-performance',
                label: '个股盈亏',
                children: <Table<PaperStockPerformance> rowKey="stock_id" size="small" columns={stockPerformanceColumns} dataSource={stockPerformance} pagination={{ pageSize: 6 }} scroll={{ x: 1060 }} />,
              },
            ]}
          />
        </Card>
      </div>
    </>
  );
}

function CompactStat({ label, value, extra }: { label: string; value: ReactNode; extra?: ReactNode }) {
  return (
    <div className="paper-stat-cell">
      <Typography.Text type="secondary">{label}</Typography.Text>
      <div className="paper-stat-value">{value ?? '-'}</div>
      {extra ? <Typography.Text className="muted paper-stat-extra">{extra}</Typography.Text> : null}
    </div>
  );
}

function orderTypeLabel(value: PaperOrder['order_type']): string {
  const labels: Record<PaperOrder['order_type'], string> = {
    market: '市价',
    limit: '限价',
    take_profit: '止盈',
    stop_loss: '止损',
  };
  return labels[value] ?? value;
}

function renderCalendarDetails(day: PaperPerformanceCalendarDay) {
  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} lg={8}>
        <Typography.Text type="secondary">当日成交</Typography.Text>
        <Space direction="vertical" size={4} className="paper-calendar-detail">
          {day.trades.map((trade) => (
            <Typography.Text key={trade.id}>
              {trade.code} {trade.side === 'buy' ? '买入' : '卖出'} {trade.quantity} 股，{formatNumber(trade.amount, 2)} 元
            </Typography.Text>
          ))}
        </Space>
      </Col>
      <Col xs={24} lg={8}>
        <Typography.Text type="secondary">委托变更</Typography.Text>
        <Space direction="vertical" size={4} className="paper-calendar-detail">
          {day.orders.map((order) => (
            <Typography.Text key={order.id}>
              {order.code} {orderTypeLabel(order.order_type)} {order.status}，成交 {order.filled_quantity}/{order.quantity}
            </Typography.Text>
          ))}
        </Space>
      </Col>
      <Col xs={24} lg={8}>
        <Typography.Text type="secondary">资金流水</Typography.Text>
        <Space direction="vertical" size={4} className="paper-calendar-detail">
          {day.cash_flows.map((flow) => (
            <Typography.Text key={flow.id}>
              {flowLabels[flow.flow_type] ?? flow.flow_type} <PriceText value={flow.amount} />
            </Typography.Text>
          ))}
        </Space>
      </Col>
    </Row>
  );
}
