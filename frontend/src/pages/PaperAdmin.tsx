import { AuditOutlined, BankOutlined, CheckCircleOutlined, LoginOutlined, LogoutOutlined, ReloadOutlined, RollbackOutlined, SafetyCertificateOutlined, StopOutlined, WalletOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Col, Empty, Form, Input, Popconfirm, Row, Select, Space, Spin, Table, Tabs, Tag, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api, formatNumber, formatTime } from '../api/client';
import PageHeader from '../components/PageHeader';
import PriceText from '../components/PriceText';
import { useBackendEvents } from '../hooks/useBackendEvents';
import type { PaperAdminAccountSummary, PaperAdminCashFlow, PaperAdminOverview } from '../types';

const PAPER_ADMIN_TOKEN_KEY = 'market-agent.paper-admin.token';
const FLOW_PAGE_SIZE = 100;

type AdminLoginValues = { username: string; password: string };
type AdminFlowFilters = { account_id?: number; flow_type?: string };
type PaperAdminProps = { onSessionCleared?: () => void };

const flowLabels: Record<string, string> = {
  buy_cost: '买入扣款',
  sell_income: '卖出入账',
  fee: '手续费',
  reset: '账户重置',
  freeze: '冻结资金',
  unfreeze: '释放冻结',
};

export default function PaperAdmin({ onSessionCleared }: PaperAdminProps = {}) {
  const [token, setToken] = useState(() => localStorage.getItem(PAPER_ADMIN_TOKEN_KEY) ?? '');
  const [overview, setOverview] = useState<PaperAdminOverview | null>(null);
  const [loading, setLoading] = useState(Boolean(token));
  const [submitting, setSubmitting] = useState(false);
  const [accountActionKey, setAccountActionKey] = useState('');
  const [filters, setFilters] = useState<AdminFlowFilters>({});
  const [flowPage, setFlowPage] = useState(1);
  const [loginForm] = Form.useForm<AdminLoginValues>();
  const [filterForm] = Form.useForm<AdminFlowFilters>();

  const load = useCallback(async (activeToken = token, showSpinner = false) => {
    if (!activeToken) return;
    if (showSpinner) setLoading(true);
    try {
      const result = await api.paperAdminOverview(activeToken, { ...filters, page: flowPage, page_size: FLOW_PAGE_SIZE });
      setOverview(result);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载管理员数据失败');
      localStorage.removeItem(PAPER_ADMIN_TOKEN_KEY);
      setToken('');
      setOverview(null);
      onSessionCleared?.();
    } finally {
      setLoading(false);
    }
  }, [filters, flowPage, token]);

  useEffect(() => {
    if (token) void load(token, true);
  }, [load, token]);

  useBackendEvents(['paper_trade.filled', 'paper_order.updated', 'paper_account.reset', 'paper_admin.account.updated', 'paper_accounts.cleared'], () => load(token, false));

  const login = async (values: AdminLoginValues) => {
    setSubmitting(true);
    try {
      const result = await api.loginPaperAdmin(values);
      localStorage.setItem(PAPER_ADMIN_TOKEN_KEY, result.token);
      setToken(result.token);
      message.success('管理员已登录');
      await load(result.token, true);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '管理员登录失败');
    } finally {
      setSubmitting(false);
    }
  };

  const clearSession = () => {
    localStorage.removeItem(PAPER_ADMIN_TOKEN_KEY);
    setToken('');
    setOverview(null);
    setFilters({});
    setFlowPage(1);
    filterForm.resetFields();
    onSessionCleared?.();
  };

  const logout = async () => {
    const activeToken = token;
    setSubmitting(true);
    try {
      if (activeToken) await api.logoutPaperAdmin(activeToken);
      message.success('管理员已退出');
    } catch {
      message.info('本地管理员登录状态已清除');
    } finally {
      clearSession();
      setSubmitting(false);
    }
  };

  const updateAccountStatus = async (account: PaperAdminAccountSummary, status: 'active' | 'suspended') => {
    if (!token) return;
    const actionKey = `${account.account_id}:${status}`;
    setAccountActionKey(actionKey);
    try {
      await api.updatePaperAdminAccount(token, account.account_id, { status });
      message.success(status === 'active' ? '账户已启用' : '账户已停用');
      await load(token, false);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '账户状态更新失败');
    } finally {
      setAccountActionKey('');
    }
  };

  const resetManagedAccount = async (account: PaperAdminAccountSummary) => {
    if (!token) return;
    const actionKey = `${account.account_id}:reset`;
    setAccountActionKey(actionKey);
    try {
      await api.resetPaperAdminAccount(token, account.account_id);
      message.success('账户已重置');
      await load(token, false);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '账户重置失败');
    } finally {
      setAccountActionKey('');
    }
  };

  const clearAllAccounts = async () => {
    if (!token) return;
    setAccountActionKey('all:clear');
    try {
      await api.clearPaperAdminAccounts(token);
      message.success('全部模拟账户已清空');
      await load(token, true);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '清空模拟账户失败');
    } finally {
      setAccountActionKey('');
    }
  };

  const accountOptions = useMemo(() => (overview?.accounts ?? []).map((account) => ({
    label: `${account.owner_name} #${account.account_id}`,
    value: account.account_id,
  })), [overview]);

  const flowTypeOptions = useMemo(() => (overview?.flow_types ?? []).map((flowType) => ({
    label: flowLabels[flowType] ?? flowType,
    value: flowType,
  })), [overview]);

  const accountColumns: ColumnsType<PaperAdminAccountSummary> = useMemo(() => [
    {
      title: '账户',
      width: 180,
      fixed: 'left',
      render: (_: unknown, row) => (
        <div className="paper-admin-account-name">
          <Typography.Text strong>{row.owner_name}</Typography.Text>
          <Typography.Text type="secondary">ID {row.account_id}</Typography.Text>
        </div>
      ),
    },
    { title: '状态', width: 90, render: (_: unknown, row) => <Tag color={row.status === 'active' ? 'green' : 'default'}>{row.status}</Tag> },
    { title: '总资产', width: 120, align: 'right', render: (_: unknown, row) => formatNumber(row.total_assets, 2) },
    { title: '现金余额', width: 120, align: 'right', render: (_: unknown, row) => formatNumber(row.cash_balance, 2) },
    { title: '可用现金', width: 120, align: 'right', render: (_: unknown, row) => formatNumber(row.cash_available, 2) },
    { title: '冻结资金', width: 110, align: 'right', render: (_: unknown, row) => formatNumber(row.cash_frozen, 2) },
    { title: '持仓市值', width: 120, align: 'right', render: (_: unknown, row) => formatNumber(row.position_market_value, 2) },
    { title: '流入', width: 110, align: 'right', render: (_: unknown, row) => formatNumber(row.flow_in, 2) },
    { title: '流出', width: 110, align: 'right', render: (_: unknown, row) => formatNumber(row.flow_out, 2) },
    { title: '净流向', width: 110, align: 'right', render: (_: unknown, row) => <PriceText value={row.net_flow} /> },
    { title: '流水数', dataIndex: 'flow_count', width: 90, align: 'right' },
    { title: '成交数', dataIndex: 'trade_count', width: 90, align: 'right' },
    { title: '最近流水', width: 170, render: (_: unknown, row) => formatTime(row.last_flow_at) },
    { title: '最近登录', width: 170, render: (_: unknown, row) => formatTime(row.last_login_at) },
  ], []);

  const accountManagementColumns: ColumnsType<PaperAdminAccountSummary> = useMemo(() => [
    {
      title: '账户',
      width: 180,
      fixed: 'left',
      render: (_: unknown, row) => (
        <div className="paper-admin-account-name">
          <Typography.Text strong>{row.owner_name}</Typography.Text>
          <Typography.Text type="secondary">ID {row.account_id}</Typography.Text>
        </div>
      ),
    },
    { title: '状态', width: 96, render: (_: unknown, row) => <Tag color={row.status === 'active' ? 'green' : 'default'}>{row.status === 'active' ? 'active' : 'suspended'}</Tag> },
    { title: '总资产', width: 120, align: 'right', render: (_: unknown, row) => formatNumber(row.total_assets, 2) },
    { title: '可用现金', width: 120, align: 'right', render: (_: unknown, row) => formatNumber(row.cash_available, 2) },
    { title: '持仓数', dataIndex: 'position_count', width: 90, align: 'right' },
    { title: '未结委托', dataIndex: 'open_order_count', width: 100, align: 'right' },
    { title: '成交数', dataIndex: 'trade_count', width: 90, align: 'right' },
    { title: '创建时间', width: 170, render: (_: unknown, row) => formatTime(row.created_at) },
    {
      title: '操作',
      width: 260,
      fixed: 'right',
      render: (_: unknown, row) => (
        <Space size={6} wrap>
          {row.status === 'active' ? (
            <Popconfirm title="停用该模拟账户？" description="停用后该账户当前会话会失效，用户需要等待管理员重新启用。" okText="停用" cancelText="取消" onConfirm={() => updateAccountStatus(row, 'suspended')}>
              <Button danger size="small" icon={<StopOutlined />} loading={accountActionKey === `${row.account_id}:suspended`}>停用</Button>
            </Popconfirm>
          ) : (
            <Button size="small" type="primary" icon={<CheckCircleOutlined />} loading={accountActionKey === `${row.account_id}:active`} onClick={() => updateAccountStatus(row, 'active')}>启用</Button>
          )}
          <Popconfirm title="重置该模拟账户？" description="该账户的持仓、委托、成交和资金流水会被清空。" okText="重置" cancelText="取消" onConfirm={() => resetManagedAccount(row)}>
            <Button size="small" icon={<RollbackOutlined />} loading={accountActionKey === `${row.account_id}:reset`}>重置</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ], [accountActionKey, token]);

  const flowColumns: ColumnsType<PaperAdminCashFlow> = useMemo(() => [
    {
      title: '账户',
      width: 170,
      fixed: 'left',
      render: (_: unknown, row) => (
        <div className="paper-admin-account-name">
          <Typography.Text strong>{row.owner_name}</Typography.Text>
          <Typography.Text type="secondary">ID {row.account_id}</Typography.Text>
        </div>
      ),
    },
    { title: '类型', width: 110, render: (_: unknown, row) => <Tag>{flowLabels[row.flow_type] ?? row.flow_type}</Tag> },
    {
      title: '股票代码',
      width: 150,
      render: (_: unknown, row) => row.code ? (
        <div className="paper-admin-account-name">
          <Typography.Text strong>{row.code}</Typography.Text>
          <Typography.Text type="secondary">{row.name ?? '-'}</Typography.Text>
        </div>
      ) : '-',
    },
    { title: '金额', width: 120, align: 'right', render: (_: unknown, row) => <PriceText value={row.amount} /> },
    { title: '余额', width: 130, align: 'right', render: (_: unknown, row) => formatNumber(row.cash_balance_after, 2) },
    { title: '委托', width: 90, align: 'right', render: (_: unknown, row) => row.order_id ?? '-' },
    { title: '成交', width: 90, align: 'right', render: (_: unknown, row) => row.trade_id ?? '-' },
    { title: '备注', dataIndex: 'remark', width: 220 },
    { title: '时间', width: 180, render: (_: unknown, row) => formatTime(row.created_at) },
  ], []);

  const applyFilters = (values: AdminFlowFilters) => {
    setFilters({
      account_id: values.account_id,
      flow_type: values.flow_type,
    });
    setFlowPage(1);
  };

  if (loading && token && !overview) return <Spin fullscreen tip="加载模拟交易管理员数据" />;

  if (!token || !overview) {
    return (
      <>
        <PageHeader title="模拟交易管理" description="管理员账户用于查看所有模拟账户的资金流向" />
        <Alert className="settings-alert" type="info" showIcon message="管理员账号为 admin，密码为 admin...。该页面只展示模拟交易账户和资金流水，不参与下单。" />
        <Row gutter={[18, 18]} className="paper-auth-grid">
          <Col xs={24} lg={10} className="paper-auth-intro-col">
            <Card className="paper-auth-intro" bordered={false}>
              <div className="paper-auth-mark"><AuditOutlined /></div>
              <Typography.Title level={3}>资金流向总览</Typography.Title>
              <Typography.Paragraph>
                管理员页面集中查看所有模拟账户的现金余额、持仓市值、流入流出和逐笔资金流水，便于对照账户交易行为。
              </Typography.Paragraph>
              <div className="paper-auth-points">
                <div className="paper-auth-point">
                  <BankOutlined />
                  <div>
                    <strong>跨账户视图</strong>
                    <span>账户资产与资金流向统一汇总展示。</span>
                  </div>
                </div>
                <div className="paper-auth-point">
                  <SafetyCertificateOutlined />
                  <div>
                    <strong>独立管理员登录</strong>
                    <span>管理员 token 与普通模拟交易账户分离。</span>
                  </div>
                </div>
              </div>
              <div className="paper-auth-facts">
                <div>
                  <span>管理员账号</span>
                  <strong>admin</strong>
                </div>
                <div>
                  <span>管理员密码</span>
                  <strong>admin...</strong>
                </div>
              </div>
            </Card>
          </Col>
          <Col xs={24} lg={8} className="paper-auth-panel-col">
            <Card className="paper-auth-panel">
              <Form form={loginForm} layout="vertical" initialValues={{ username: 'admin' }} onFinish={login}>
                <Typography.Title level={4}>管理员登录</Typography.Title>
                <Form.Item name="username" label="账号" rules={[{ required: true, message: '请输入管理员账号' }]}>
                  <Input prefix={<AuditOutlined />} placeholder="admin" autoComplete="username" />
                </Form.Item>
                <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入管理员密码' }]}>
                  <Input.Password minLength={6} placeholder="admin..." autoComplete="current-password" />
                </Form.Item>
                <Form.Item className="paper-auth-submit">
                  <Button type="primary" htmlType="submit" icon={<LoginOutlined />} loading={submitting} block>登录管理页</Button>
                </Form.Item>
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
        title="模拟交易管理"
        description={`管理员 ${overview.admin.username} · 账户资金流向`}
        extra={(
          <Space wrap>
            <Button icon={<ReloadOutlined />} onClick={() => load(token, true)}>刷新</Button>
            <Button icon={<LogoutOutlined />} loading={submitting} onClick={logout}>退出</Button>
          </Space>
        )}
      />

      <Alert className="settings-alert" type="info" showIcon message="当前为管理员管理视图，普通模拟账户 token 不能访问该页面的数据接口；停用账户会撤销该账户当前登录会话。" />

      <div className="paper-admin-layout">
        <Card title={<Space><WalletOutlined />资金总览</Space>} className="paper-account-card">
          <div className="paper-stat-grid paper-admin-stat-grid">
            <AdminStat label="账户数" value={overview.totals.account_count} extra={`成交 ${overview.totals.trade_count} 笔`} />
            <AdminStat label="总资产" value={`${formatNumber(overview.totals.total_assets, 2)} 元`} />
            <AdminStat label="可用现金" value={`${formatNumber(overview.totals.cash_available, 2)} 元`} />
            <AdminStat label="持仓市值" value={`${formatNumber(overview.totals.position_market_value, 2)} 元`} />
            <AdminStat label="资金流入" value={`${formatNumber(overview.totals.flow_in, 2)} 元`} />
            <AdminStat label="资金流出" value={`${formatNumber(overview.totals.flow_out, 2)} 元`} />
            <AdminStat label="净流向" value={<PriceText value={overview.totals.net_flow} />} extra={`流水 ${overview.totals.flow_count} 条`} />
            <AdminStat label="冻结资金" value={`${formatNumber(overview.totals.cash_frozen, 2)} 元`} />
          </div>
        </Card>

        <Card title={<Space><AuditOutlined />账户与流水</Space>} className="paper-admin-records">
          <Tabs
            size="small"
            items={[
              {
                key: 'account-management',
                label: '账户管理',
                children: (
                  <>
                    <div className="paper-admin-tab-toolbar">
                      <Typography.Text type="secondary">停用账户会撤销当前会话；重置会清空该账户持仓、委托、成交和流水。</Typography.Text>
                      <Popconfirm title="清空全部模拟账户？" description="该操作会删除全部模拟账户及相关持仓、委托、成交、流水和通知。" okText="清空全部" cancelText="取消" onConfirm={clearAllAccounts}>
                        <Button danger size="small" loading={accountActionKey === 'all:clear'}>清空全部账户</Button>
                      </Popconfirm>
                    </div>
                    {overview.accounts.length ? (
                      <Table<PaperAdminAccountSummary>
                        rowKey="account_id"
                        size="small"
                        columns={accountManagementColumns}
                        dataSource={overview.accounts}
                        pagination={{ pageSize: 10 }}
                        scroll={{ x: 1320 }}
                      />
                    ) : <Empty description="暂无模拟账户" />}
                  </>
                ),
              },
              {
                key: 'accounts',
                label: '账户资金',
                children: overview.accounts.length ? (
                  <Table<PaperAdminAccountSummary>
                    rowKey="account_id"
                    size="small"
                    columns={accountColumns}
                    dataSource={overview.accounts}
                    pagination={{ pageSize: 10 }}
                    scroll={{ x: 1600 }}
                  />
                ) : <Empty description="暂无模拟账户" />,
              },
              {
                key: 'flows',
                label: '资金流水',
                children: (
                  <>
                    <Form form={filterForm} layout="vertical" onFinish={applyFilters} className="paper-admin-filter">
                      <Row gutter={[12, 0]}>
                        <Col xs={24} md={8}>
                          <Form.Item name="account_id" label="账户">
                            <Select allowClear placeholder="全部账户" options={accountOptions} />
                          </Form.Item>
                        </Col>
                        <Col xs={24} md={8}>
                          <Form.Item name="flow_type" label="流水类型">
                            <Select allowClear placeholder="全部类型" options={flowTypeOptions} />
                          </Form.Item>
                        </Col>
                        <Col xs={24} md={8} className="paper-admin-filter-actions">
                          <Space wrap>
                            <Button type="primary" htmlType="submit">筛选</Button>
                            <Button onClick={() => {
                              filterForm.resetFields();
                              setFilters({});
                              setFlowPage(1);
                            }}>重置</Button>
                          </Space>
                        </Col>
                      </Row>
                    </Form>
                    <Table<PaperAdminCashFlow>
                      rowKey="id"
                      size="small"
                      columns={flowColumns}
                      dataSource={overview.flows.items}
                      pagination={{
                        current: overview.flows.page ?? flowPage,
                        pageSize: overview.flows.page_size ?? FLOW_PAGE_SIZE,
                        total: overview.flows.total,
                        showSizeChanger: false,
                        onChange: (page) => setFlowPage(page),
                      }}
                      scroll={{ x: 1250 }}
                    />
                  </>
                ),
              },
            ]}
          />
        </Card>
      </div>
    </>
  );
}

function AdminStat({ label, value, extra }: { label: string; value: ReactNode; extra?: ReactNode }) {
  return (
    <div className="paper-stat-cell">
      <Typography.Text type="secondary">{label}</Typography.Text>
      <div className="paper-stat-value">{value ?? '-'}</div>
      {extra ? <Typography.Text className="muted paper-stat-extra">{extra}</Typography.Text> : null}
    </div>
  );
}
