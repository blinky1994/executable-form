import { Component, type ReactNode, useEffect, useMemo, useState } from 'react';
import { useForm, useStore } from '@tanstack/react-form';
import { keepPreviousData, useQueries, useQuery } from '@tanstack/react-query';
import { CheckCircle2, CloudCog, Loader2, ShieldAlert } from 'lucide-react';

import { evaluateForm, resolveAsyncRequest } from '../api';
import type { FormField, FormOutput } from '../types';

type Values = Record<string, unknown>;

export type DynamicFormProps = {
  formId: string;
  title: string;
  subtitle: string;
  context?: Record<string, unknown>;
  submitLabel?: string;
};

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timeout);
  }, [value, delayMs]);

  return debounced;
}

function stripHiddenFields(output: FormOutput | undefined, values: Values): Values {
  if (!output) return values;

  return Object.fromEntries(
    output.fields
      .filter((field) => field.visible)
      .map((field) => [field.id, values[field.id] ?? field.value]),
  );
}

function coerceFieldValue(field: FormField, nextValue: string | boolean): unknown {
  if (field.type === 'checkbox') return Boolean(nextValue);
  if (field.type === 'number') return nextValue === '' ? undefined : Number(nextValue);
  return nextValue;
}

function fieldDisplayValue(field: FormField, values: Values): unknown {
  return values[field.id] ?? field.value;
}

function groupVisibleFields(fields: FormField[]): Array<[string, FormField[]]> {
  const groups = new Map<string, FormField[]>();

  for (const field of fields) {
    const section = field.section || 'Fields';
    groups.set(section, [...(groups.get(section) ?? []), field]);
  }

  return Array.from(groups.entries());
}

class FieldErrorBoundary extends Component<
  { fieldId: string; children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidUpdate(previousProps: { fieldId: string }) {
    if (previousProps.fieldId !== this.props.fieldId && this.state.failed) {
      this.setState({ failed: false });
    }
  }

  render() {
    if (this.state.failed) {
      return (
        <div className="fieldRenderError">
          Unable to render field <strong>{this.props.fieldId}</strong>.
        </div>
      );
    }

    return this.props.children;
  }
}

function FieldRenderer({
  field,
  value,
  onChange,
}: {
  field: FormField;
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  if (!field.visible) return null;

  const describedBy = field.errors.length ? `${field.id}-errors` : undefined;

  return (
    <label className="field">
      <span className="fieldLabel">
        {field.label}
        {field.required ? <span aria-hidden="true">*</span> : null}
      </span>

      {field.type === 'select' ? (
        <select
          value={String(value ?? '')}
          disabled={field.disabled || field.loading}
          aria-describedby={describedBy}
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">{field.loading ? 'Loading...' : 'Select one'}</option>
          {field.options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      ) : null}

      {field.type === 'text' || field.type === 'date' ? (
        <input
          type={field.type === 'date' ? 'date' : 'text'}
          value={String(value ?? '')}
          disabled={field.disabled}
          aria-describedby={describedBy}
          onChange={(event) => onChange(event.target.value)}
        />
      ) : null}

      {field.type === 'file' ? (
        <input
          type="file"
          disabled={field.disabled}
          aria-describedby={describedBy}
          onChange={(event) => {
            const files = Array.from(event.target.files ?? []).map((file) => ({
              name: file.name,
              size: file.size,
              type: file.type,
            }));
            onChange(files);
          }}
        />
      ) : null}

      {field.type === 'number' ? (
        <input
          type="number"
          value={value === undefined || value === null ? '' : String(value)}
          disabled={field.disabled}
          aria-describedby={describedBy}
          onChange={(event) => onChange(coerceFieldValue(field, event.target.value))}
        />
      ) : null}

      {field.type === 'checkbox' ? (
        <span className="checkboxRow">
          <input
            type="checkbox"
            checked={Boolean(value)}
            disabled={field.disabled}
            aria-describedby={describedBy}
            onChange={(event) => onChange(event.target.checked)}
          />
          <span>{Boolean(value) ? 'Enabled' : 'Disabled'}</span>
        </span>
      ) : null}

      {field.loading ? (
        <span className="fieldHint">
          <Loader2 size={14} className="spin" /> Loading resource metadata
        </span>
      ) : null}

      {field.errors.length ? (
        <span id={`${field.id}-errors`} className="fieldError">
          {field.errors.join(' ')}
        </span>
      ) : null}
    </label>
  );
}

export function DynamicForm({
  formId,
  title,
  subtitle,
  context = {},
  submitLabel = 'Submit',
}: DynamicFormProps) {
  const [asyncResults, setAsyncResults] = useState<Record<string, unknown>>({});
  const [lastSubmitted, setLastSubmitted] = useState<Values | null>(null);
  const contextKey = useMemo(() => JSON.stringify(context), [context]);

  const form = useForm({
    defaultValues: {} as Values,
    onSubmit: () => {
      setLastSubmitted(stripHiddenFields(evaluation.data, values));
    },
  });
  const values = useStore(form.store, (state) => state.values as Values);
  const debouncedValues = useDebouncedValue(values, 350);

  useEffect(() => {
    form.reset({});
    setAsyncResults({});
    setLastSubmitted(null);
  }, [contextKey, form, formId]);

  const evaluation = useQuery({
    queryKey: ['evaluate-form', formId, contextKey, debouncedValues, asyncResults],
    queryFn: ({ signal }) =>
      evaluateForm(
        formId,
        {
          state: debouncedValues,
          context,
          async_results: asyncResults,
        },
        signal,
      ),
    placeholderData: keepPreviousData,
  });

  const pendingAsyncRequests = useMemo(
    () =>
      evaluation.data?.async_requests.filter(
        (request) => asyncResults[request.id] === undefined,
      ) ?? [],
    [asyncResults, evaluation.data?.async_requests],
  );

  const asyncRequestResults = useQueries({
    queries: pendingAsyncRequests.map((request) => ({
      queryKey: ['form-async-request', formId, request.id, request.type, request.params],
      queryFn: ({ signal }) => resolveAsyncRequest(formId, request, signal),
      staleTime: Infinity,
      gcTime: Infinity,
    })),
  });

  useEffect(() => {
    const resolved = asyncRequestResults
      .map((query) => query.data)
      .filter((result) => result && asyncResults[result.id] === undefined);

    if (resolved.length) {
      setAsyncResults((current) => {
        const next = { ...current };
        for (const result of resolved) {
          if (result) {
            next[result.id] = result.result;
          }
        }
        return next;
      });
    }
  }, [asyncRequestResults, asyncResults]);

  const visibleFields = useMemo(
    () => evaluation.data?.fields.filter((field) => field.visible) ?? [],
    [evaluation.data],
  );
  const fieldGroups = useMemo(() => groupVisibleFields(visibleFields), [visibleFields]);

  const hiddenSubmitPreview = useMemo(
    () => stripHiddenFields(evaluation.data, values),
    [evaluation.data, values],
  );

  const visibleFormErrors = useMemo(
    () => evaluation.data?.form_errors ?? [],
    [evaluation.data?.form_errors],
  );

  const isInitialLoading = evaluation.isPending && !evaluation.data;
  const isQuietlyUpdating = evaluation.isFetching && Boolean(evaluation.data);
  const isResolvingAsync = asyncRequestResults.some((query) => query.isFetching);

  function updateValue(field: FormField, nextValue: unknown) {
    form.setFieldValue(field.id, nextValue);
    setLastSubmitted(null);
  }

  return (
    <main className="appShell">
      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Executable Forms Prototype</p>
            <h1>{title}</h1>
          </div>
          <div className={`statusPill ${evaluation.data?.can_submit ? 'ok' : 'warn'}`}>
            {isInitialLoading || isResolvingAsync ? (
              <Loader2 size={16} className="spin" />
            ) : evaluation.data?.can_submit ? (
              <CheckCircle2 size={16} />
            ) : (
              <ShieldAlert size={16} />
            )}
            {evaluation.data?.can_submit ? 'Ready' : 'Needs input'}
          </div>
        </header>

        <form
          className="formSurface"
          onSubmit={(event) => {
            event.preventDefault();
            event.stopPropagation();
            form.handleSubmit();
          }}
        >
          <div className="formHeader">
            <CloudCog size={22} />
            <div>
              <h2>{subtitle}</h2>
              <p>Backend Python owns the rules. React renders the returned fields.</p>
            </div>
          </div>

          {evaluation.isError ? (
            <div className="callout error">Evaluation failed. Check that FastAPI is running.</div>
          ) : null}

          {visibleFormErrors.map((error) => (
            <div key={error} className="callout">
              {error}
            </div>
          ))}

          {isQuietlyUpdating ? <div className="quietUpdate">Updating rules...</div> : null}

          {fieldGroups.map(([section, fields]) => (
            <section key={section} className="fieldSection">
              {section !== 'Fields' ? <h3>{section}</h3> : null}
              <div className="fieldGrid">
                {fields.map((field) => (
                  <FieldErrorBoundary key={field.id} fieldId={field.id}>
                    <form.Field name={field.id}>
                      {() => (
                        <FieldRenderer
                          field={field}
                          value={fieldDisplayValue(field, values)}
                          onChange={(value) => updateValue(field, value)}
                        />
                      )}
                    </form.Field>
                  </FieldErrorBoundary>
                ))}
              </div>
            </section>
          ))}

          <div className="actions">
            <button type="submit" disabled={!evaluation.data?.can_submit}>
              {submitLabel}
            </button>
          </div>
        </form>
      </section>

      <aside className="inspector">
        <h2>Submit Payload</h2>
        <p>Hidden fields are stripped before submit.</p>
        <pre>{JSON.stringify(lastSubmitted ?? hiddenSubmitPreview, null, 2)}</pre>
      </aside>
    </main>
  );
}
