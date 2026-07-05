import { CloseCircleOutlined, LoginOutlined, ReloadOutlined, ShoppingCartOutlined, SyncOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Col, Form, Input, InputNumber, Popconfirm, Radio, Row, Select, Space, Spin, Table, Tag, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api, formatNumber, formatTime } from '../api/client';
import MetricCard from '../components/MetricCard';
import PageHeader from '../components/PageHeader';
import PriceText from '../components/PriceText';
import StockLink from '../components/StockLink';
import { useBackendEvents } from '../hooks/useBackendEvents';
import type { PaperCashFlow, PaperOrder, PaperPerformanceCalendarDay, PaperPerformanceSummary, PaperPosition, PaperStockPerformance, PaperSummary, PaperTrade } from '../types';

const PAPER_TOKEN_KEY = 'market-agent.paper-trading.token';

type AccountFormValues = { owner_name: string; password: string };
type OrderFormValues = { code: string; side: 'buy' | 'sell'; order_type: string; quantity: number; limit_price?: number | null; trigger_price?: number | null };
type OrderFilterValues = { code?: string; side?: 'buy' | 'sell'; order_type?: PaperOrder['order_type']; status?: string };

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
};

export default function PaperTrading() {
  const [searchParams] = useSearchParams();
  const [token, setToken] = useState(() => localStorage.getItem(PAPER_TOKEN_KEY) ?? '');
  const [loading, setLoading] = useState(Boolean(token));
  const [submitting, setSubmitting] = useState(false);
  const [matching, setMatching] = useState(false);
  const [summary, setSummary] = useState<PaperSummary | null>(null);
  const [performance, setPerformance] = useState<PaperPerformanceSummary | null>(null);
  const [stockPerformance, setStockPerformance] = useState<PaperStockPerformance[]>([]);
  const [calendarDays, setCalendarDays] = useState<PaperPerformanceCalendarDay[]>([]);
  const [orderFilters, setOrderFilters] = useState<OrderFilterValues>({});
  const [positions, setPositions] = useState<PaperPosition[]>([]);
  const [orders, setOrders] = useState<PaperOrder[]>([]);
  const [trades, setTrades] = useState<PaperTrade[]>([]);
  const [flows, setFlows] = useState<PaperCashFlow[]>([]);
  const [loginForm] = Form.useForm<AccountFormValues>();
  const [createForm] = Form.useForm<AccountFormValues>();
  const [orderForm] = Form.useForm<OrderFormValues>();
  const [orderFilterForm] = Form.useForm<OrderFilterValues>();
  const orderType = Form.useWatch('order_type', orderForm);
  const queryCode = searchParams.get('code')?.toUpperCase();

  const load = useCallback(async (activeToken = token, showSpinner = false) => {
    if (!activeToken) return;
    if (showSpinner) setLoading(true);
    try {
      const [summaryRes, performanceRes, stockPerformanceRes, calendarRes, positionsRes, ordersRes, tradesRes, flowsRes] = await Promise.all([
        api.paperSummary(activeToken),
        api.paperPerformanceSummary(activeToken),
        api.paperPerformanceByStock(activeToken),
        api.paperPerformanceCalendar(activeToken),
        api.paperPositions(activeToken),
        api.paperOrders(activeToken, orderFilters),
        api.paperTrades(activeToken),
        api.paperCashFlows(activeToken),
      ]);
      setSummary(summaryRes);
      setPerformance(performanceRes);
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
      setStockPerformance([]);
      setCalendarDays([]);
    } finally {
      if (showSpinner) setLoading(false);
      else setLoading(false);
    }
  }, [orderFilters, token]);

  useEffect(() => {
    if (token) void load(token, true);
  }, [load, token]);

  useEffect(() => {
    if (queryCode) orderForm.setFieldsValue({ code: queryCode, side: 'buy', order_type: 'market', quantity: 100 });
  }, [orderForm, queryCode]);

  useBackendEvents(['paper_trade.filled', 'paper_order.updated', 'paper_account.reset'], () => load(token, false));

  const login = async (values: AccountFormValues) => {
    setSubmitting(true);
    try {
      const result = await api.loginPaperAccount(values);
      localStorage.setItem(PAPER_TOKEN_KEY, result.token);
      setToken(result.token);
      message.success('已登录模拟交易账户');
      await load(result.token, true);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '登录失败');
    } finally {
      setSubmitting(false);
    }
  };

  const createAccount = async (values: AccountFormValues) => {
    setSubmitting(true);
    try {
      await api.createPaperAccount(values);
      const result = await api.loginPaperAccount(values);
      localStorage.setItem(PAPER_TOKEN_KEY, result.token);
      setToken(result.token);
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
    setStockPerformance([]);
    setCalendarDays([]);
    setPositions([]);
    setOrders([]);
    setTrades([]);
    setFlows([]);
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

  const submitOrder = async (values: OrderFormValues) => {
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

  const positionColumns: ColumnsType<PaperPosition> = useMemo(() => [
    { title: '股票', width: 150, render: (_: unknown, row) => <StockLink code={row.code} name={row.name} /> },
    { title: '持仓', dataIndex: 'total_quantity', width: 90, align: 'right' },
    { title: '可卖', dataIndex: 'available_quantity', width: 90, align: 'right' },
    { title: '成本', width: 90, align: 'right', render: (_: unknown, row) => formatNumber(row.avg_cost, 4) },
    { title: '现价', width: 90, align: 'right', render: (_: unknown, row) => formatNumber(row.market_price, 2) },
    { title: '市值', width: 110, align: 'right', render: (_: unknown, row) => formatNumber(row.market_value, 2) },
    { title: '浮盈亏', width: 110, align: 'right', render: (_: unknown, row) => <PriceText value={row.floating_pnl} /> },
    { title: '收益率', width: 100, align: 'right', render: (_: unknown, row) => <PriceText value={row.floating_pnl_pct} suffix="%" /> },
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

  if (loading && token && !summary) return <Spin fullscreen tip="加载模拟交易账户" />;

  if (!token || !summary) {
    return (
      <>
        <PageHeader title="模拟交易" description="使用真实行情快照进行本地虚拟交易" />
        <Alert className="settings-alert" type="warning" showIcon message="模拟交易仅用于课程项目和学习验证，不构成真实投资建议。" />
        <Row gutter={[16, 16]} className="paper-auth-grid">
          <Col xs={24} lg={12}>
            <Card title="登录账户">
              <Form form={loginForm} layout="vertical" onFinish={login}>
                <Form.Item name="owner_name" label="账户名" rules={[{ required: true, message: '请输入账户名' }]}>
                  <Input autoComplete="username" />
                </Form.Item>
                <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
                  <Input.Password autoComplete="current-password" />
                </Form.Item>
                <Button type="primary" htmlType="submit" icon={<LoginOutlined />} loading={submitting}>登录</Button>
              </Form>
            </Card>
          </Col>
          <Col xs={24} lg={12}>
            <Card title="创建账户">
              <Form form={createForm} layout="vertical" onFinish={createAccount}>
                <Form.Item name="owner_name" label="账户名" rules={[{ required: true, message: '请输入账户名' }, { min: 2, message: '至少 2 个字符' }]}>
                  <Input autoComplete="username" />
                </Form.Item>
                <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }, { min: 6, message: '至少 6 个字符' }]}>
                  <Input.Password autoComplete="new-password" />
                </Form.Item>
                <Button htmlType="submit" loading={submitting}>创建并登录</Button>
              </Form>
            </Card>
          </Col>
        </Row>
      </>
    );
  }

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

      <Alert className="settings-alert" type="warning" showIcon message="已启用账户、市价单、限价委托、止盈止损条件单、撤单、冻结资金/持仓、成交和资金流水；更完整交易时间和涨跌停规则将在后续阶段开放。" />

      <div className="paper-summary-grid">
        <MetricCard title="总资产" value={summary.total_assets} />
        <MetricCard title="可用现金" value={summary.cash_available} />
        <MetricCard title="冻结资金" value={summary.cash_frozen} />
        <MetricCard title="持仓市值" value={summary.position_market_value} />
        <MetricCard title="成交次数" value={summary.trade_count} />
      </div>

      <div className="paper-summary-grid section-gap">
        <MetricCard title="已实现盈亏" value={performance?.realized_pnl} change={performance?.total_return_pct ?? null} />
        <MetricCard title="胜率" value={performance?.win_rate_pct} suffix="%" extra={`${performance?.winning_trades ?? 0}/${performance?.closed_trade_count ?? 0} 笔`} />
        <MetricCard title="平均盈亏" value={performance?.average_pnl} extra={`盈利 ${formatNumber(performance?.average_profit, 2)} / 亏损 ${formatNumber(performance?.average_loss, 2)}`} />
        <MetricCard title="最大单笔盈利" value={performance?.max_single_profit} extra={`闭合 ${performance?.closed_trade_count ?? 0} 笔`} />
        <MetricCard title="最大单笔亏损" value={performance?.max_single_loss} extra={`总收益率 ${formatNumber(performance?.total_return_pct, 2)}%`} />
      </div>

      <div className="section-gap">
        <Card title="个股盈亏明细">
          <Table<PaperStockPerformance> rowKey="stock_id" size="small" columns={stockPerformanceColumns} dataSource={stockPerformance} pagination={{ pageSize: 6 }} scroll={{ x: 1060 }} />
        </Card>
      </div>

      <div className="section-gap">
        <Card title="交易日历">
          <Table<PaperPerformanceCalendarDay>
            rowKey="trade_date"
            size="small"
            columns={calendarColumns}
            dataSource={calendarDays}
            pagination={{ pageSize: 6 }}
            scroll={{ x: 830 }}
            expandable={{ expandedRowRender: renderCalendarDetails }}
          />
        </Card>
      </div>

      <Row gutter={[16, 16]} className="section-gap">
        <Col xs={24} xl={8}>
          <Card title={<Space><ShoppingCartOutlined />下单面板</Space>} className="paper-order-card">
            <Form
              form={orderForm}
              layout="vertical"
              initialValues={{ code: queryCode ?? '', side: 'buy', order_type: 'market', quantity: 100 }}
              onFinish={submitOrder}
            >
              <Form.Item name="code" label="股票代码" rules={[{ required: true, message: '请输入股票代码' }]}>
                <Input placeholder="例如 300308.SZ" />
              </Form.Item>
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
          <Card title="持仓">
            <Table<PaperPosition> rowKey="stock_id" size="small" columns={positionColumns} dataSource={positions} pagination={false} scroll={{ x: 900 }} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} className="section-gap">
        <Col xs={24} xl={12}>
          <Card title="委托记录">
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
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title="成交记录">
            <Table<PaperTrade> rowKey="id" size="small" columns={tradeColumns} dataSource={trades} pagination={{ pageSize: 6 }} scroll={{ x: 900 }} />
          </Card>
        </Col>
      </Row>

      <div className="section-gap">
        <Card title="资金流水">
          <Table<PaperCashFlow> rowKey="id" size="small" columns={flowColumns} dataSource={flows} pagination={{ pageSize: 8 }} scroll={{ x: 720 }} />
        </Card>
      </div>
    </>
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
