import { KeyOutlined, SaveOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Col, Form, Input, Row, Select, Space, Tag } from 'antd';
import { useEffect } from 'react';
import type { NewsLlmConfig, NewsLlmConfigPayload } from '../../types';

type Props = {
  config: NewsLlmConfig | null;
  loading: boolean;
  onSave: (payload: NewsLlmConfigPayload) => Promise<void>;
};

export default function NewsLlmConfigCard({ config, loading, onSave }: Props) {
  const [form] = Form.useForm<NewsLlmConfigPayload>();

  useEffect(() => {
    if (!config) return;
    form.setFieldsValue({
      provider: config.provider,
      api_base_url: config.api_base_url,
      model: config.model,
      api_key: '',
      prompt_preset: config.prompt_preset,
      custom_prompt: config.custom_prompt ?? '',
    });
  }, [config, form]);

  const submit = async (values: NewsLlmConfigPayload) => {
    const apiKey = values.api_key?.trim();
    await onSave({
      provider: values.provider.trim(),
      api_base_url: values.api_base_url.trim(),
      model: values.model.trim(),
      api_key: apiKey || null,
      prompt_preset: values.prompt_preset,
      custom_prompt: values.custom_prompt?.trim() || null,
    });
    form.setFieldValue('api_key', '');
  };

  return (
    <Card
      title={<Space><KeyOutlined />新闻 LLM 配置</Space>}
      className="section-gap"
      extra={<Tag color={config?.api_key_configured ? 'green' : 'orange'}>{config?.api_key_configured ? 'Key 已配置' : 'Key 未配置'}</Tag>}
    >
      <Alert
        type="info"
        showIcon
        className="settings-alert"
        message="默认 Prompt 会在没有自定义 Prompt 时生效；API Key 只保存在后端，前端不会回显。"
      />
      <Form<NewsLlmConfigPayload> form={form} layout="vertical" onFinish={submit} className="settings-form">
        <Row gutter={[16, 0]}>
          <Col xs={24} md={8}>
            <Form.Item label="Provider" name="provider" rules={[{ required: true, message: '请输入 Provider' }]}>
              <Input placeholder="deepseek" />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item label="Model" name="model" rules={[{ required: true, message: '请输入 Model' }]}>
              <Input placeholder="deepseek-v4-flash" />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item label="API Key" name="api_key">
              <Input.Password autoComplete="new-password" placeholder={config?.api_key_configured ? '保持为空则不修改' : '请输入 API Key'} />
            </Form.Item>
          </Col>
          <Col xs={24}>
            <Form.Item label="Base URL" name="api_base_url" rules={[{ required: true, message: '请输入 Base URL' }]}>
              <Input placeholder="https://api.deepseek.com" />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item label="Prompt 预设" name="prompt_preset" rules={[{ required: true, message: '请选择 Prompt 预设' }]}>
              <Select options={[{ label: '默认简化', value: 'default' }]} />
            </Form.Item>
          </Col>
          <Col xs={24} md={16}>
            <Form.Item label="自定义 Prompt" name="custom_prompt">
              <Input.TextArea rows={4} placeholder={config?.default_prompt ?? '默认 Prompt'} />
            </Form.Item>
          </Col>
        </Row>
        <Space wrap>
          <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={loading}>保存 LLM 配置</Button>
          <span className="muted">当前生效：{config?.custom_prompt_configured ? '自定义 Prompt' : '默认 Prompt'}</span>
        </Space>
      </Form>
    </Card>
  );
}
