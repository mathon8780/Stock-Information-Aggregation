import { LoginOutlined, ReloadOutlined, ShoppingCartOutlined } from '@ant-design/icons';
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
import type { PaperCashFlow, PaperOrder, PaperPosition, PaperSummary, PaperTrade } from '../types';

const PAPER_TOKEN_KEY = 'market-agent.paper-trading.token';

type AccountFormValues = { owner_name: string; password: string };
type OrderFormValues = { code: string; side: 'buy' | 'sell'; order_type: string; quantity: number };

const orderStatusColor: Record<string, string> = {
  filled: 'green',
  pending: 'blue',
  monitoring: 'gold',
  cancelled: 'default',
  rejected: 'red',
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
  const [summary, setSummary] = useState<PaperSummary | null>(null);
  const [positions, setPositions] = useState<PaperPosition[]>([]);
  const [orders, setOrders] = useState<PaperOrder[]>([]);
  const [trades, setTrades] = useState<PaperTrade[]>([]);
  const [flows, setFlows] = useState<PaperCashFlow[]>([]);
  const [loginForm] = Form.useForm<AccountFormValues>();
  const [createForm] = Form.useForm<AccountFormValues>();
  const [orderForm] = Form.useForm<OrderFormValues>();
  const queryCode = searchParams.get('code')?.toUpperCase();

  const load = useCallback(async (activeToken = token, showSpinner = false) => {
    if (!activeToken) return;
    if (showSpinner) setLoading(true);
    try {
      const [summaryRes, positionsRes, ordersRes, tradesRes, flowsRes] = await Promise.all([
        api.paperSummary(activeToken),
        api.paperPositions(activeToken),
        api.paperOrders(activeToken),
        api.paperTrades(activeToken),
        api.paperCashFlows(activeToken),
      ]);
      setSummary(summaryRes);
      setPositions(positionsRes.items);
      setOrders(ordersRes.items);
      setTrades(tradesRes.items);
      setFlows(flowsRes.items);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载模拟交易账户失败');
      localStorage.removeItem(PAPER_TOKEN_KEY);
      setToken('');
      setSummary(null);
    } finally {
      if (showSpinner) setLoading(false);
      else setLoading(false);
    }
  }, [token]);

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

  const logout = () => {
    localStorage.removeItem(PAPER_TOKEN_KEY);
    setToken('');
    setSummary(null);
    setPositions([]);
    setOrders([]);
    setTrades([]);
    setFlows([]);
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
      });
      message.success('市价委托已成交');
      await load(token, false);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '下单失败');
    } finally {
      setSubmitting(false);
    }
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

  const orderColumns: ColumnsType<PaperOrder> = useMemo(() => [
    { title: '股票', width: 150, render: (_: unknown, row) => <StockLink code={row.code} name={row.name} /> },
    { title: '方向', width: 70, render: (_: unknown, row) => <Tag color={row.side === 'buy' ? 'red' : 'green'}>{row.side === 'buy' ? '买入' : '卖出'}</Tag> },
    { title: '类型', width: 80, render: (_: unknown, row) => row.order_type === 'market' ? '市价' : row.order_type },
    { title: '状态', width: 90, render: (_: unknown, row) => <Tag color={orderStatusColor[row.status] ?? 'default'}>{row.status}</Tag> },
    { title: '数量', dataIndex: 'quantity', width: 90, align: 'right' },
    { title: '成交价', width: 90, align: 'right', render: (_: unknown, row) => formatNumber(row.avg_fill_price, 2) },
    { title: '费用', width: 90, align: 'right', render: (_: unknown, row) => formatNumber(row.fee_total, 2) },
    { title: '时间', width: 170, render: (_: unknown, row) => formatTime(row.created_at) },
  ], []);

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
            <Popconfirm title="重置模拟账户？" description="持仓、委托、成交和流水会被清空。" okText="重置" cancelText="取消" onConfirm={resetAccount}>
              <Button danger loading={submitting}>重置账户</Button>
            </Popconfirm>
            <Button onClick={logout}>退出</Button>
          </Space>
        )}
      />

      <Alert className="settings-alert" type="warning" showIcon message="首版已启用账户、市价买入/卖出、持仓、成交和资金流水；限价单、条件单和完整撮合规则将在后续阶段开放。" />

      <div className="paper-summary-grid">
        <MetricCard title="总资产" value={summary.total_assets} />
        <MetricCard title="可用现金" value={summary.cash_available} />
        <MetricCard title="持仓市值" value={summary.position_market_value} />
        <MetricCard title="成交次数" value={summary.trade_count} />
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
                <Select options={[{ label: '市价单', value: 'market' }, { label: '限价单（后续开放）', value: 'limit', disabled: true }, { label: '止盈/止损（后续开放）', value: 'stop_loss', disabled: true }]} />
              </Form.Item>
              <Form.Item name="quantity" label="数量" rules={[{ required: true, message: '请输入数量' }]}>
                <InputNumber min={100} step={100} precision={0} className="paper-quantity-input" />
              </Form.Item>
              <Button type="primary" htmlType="submit" loading={submitting} block>提交市价委托</Button>
            </Form>
            <Typography.Text className="muted paper-order-note">买入数量按 100 股整数倍校验，成交价取最新自选股快照、全市场快照或日 K 收盘价。</Typography.Text>
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
            <Table<PaperOrder> rowKey="id" size="small" columns={orderColumns} dataSource={orders} pagination={{ pageSize: 6 }} scroll={{ x: 840 }} />
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
