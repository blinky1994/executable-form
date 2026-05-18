export type FieldType = 'text' | 'number' | 'select' | 'checkbox' | 'date' | 'file';

export type FieldOption = {
  value: string;
  label: string;
};

export type FormField = {
  id: string;
  type: FieldType;
  label: string;
  section?: string | null;
  visible: boolean;
  required: boolean;
  disabled: boolean;
  loading: boolean;
  value: unknown;
  options: FieldOption[];
  errors: string[];
};

export type AsyncRequest = {
  id: string;
  type: string;
  params: Record<string, unknown>;
};

export type AsyncResult = {
  id: string;
  result: unknown;
};

export type EvaluationRequest = {
  state: Record<string, unknown>;
  context: Record<string, unknown>;
  async_results: Record<string, unknown>;
};

export type FormOutput = {
  version: string;
  fields: FormField[];
  async_requests: AsyncRequest[];
  form_errors: string[];
  can_submit: boolean;
};

export type FormConfig = {
  formId: string;
  title: string;
  subtitle: string;
  context: Record<string, unknown>;
  submitLabel: string;
};
