import { useState } from 'react'
import SetupFormActions from '../setup/SetupFormActions'
import ValidationMessage from '../setup/ValidationMessage'

export default function FranchiseForm({
  initialValues = {},
  onSubmit,
  onCancel,
  onDeactivate,
  onReactivate,
  saving = false,
  error = null,
}) {
  const [values, setValues] = useState({
    name: initialValues.name ?? '',
    description: initialValues.description ?? '',
    display_order: initialValues.display_order ?? '',
    notes: initialValues.notes ?? '',
  })
  const [fieldErrors, setFieldErrors] = useState({})

  function handleChange(field) {
    return (event) => {
      setValues((prev) => ({ ...prev, [field]: event.target.value }))
      if (fieldErrors[field]) {
        setFieldErrors((prev) => ({ ...prev, [field]: undefined }))
      }
    }
  }

  function validate() {
    const errors = {}
    if (!values.name.trim()) errors.name = 'Name is required'
    return errors
  }

  function handleSave() {
    const errors = validate()
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors)
      return
    }
    onSubmit({
      name: values.name.trim(),
      description: values.description.trim() || null,
      display_order: values.display_order !== '' ? Number(values.display_order) : null,
      notes: values.notes.trim() || null,
    })
  }

  const isActive = initialValues.is_active !== false

  return (
    <form
      className="space-y-5"
      data-testid="franchise-form"
      onSubmit={(event) => { event.preventDefault(); handleSave() }}
    >
      <ValidationMessage message={error} fieldErrors={fieldErrors} />

      <div>
        <label htmlFor="franchise-name" className="block text-sm font-medium text-gray-700 mb-1">
          Name <span className="text-red-500">*</span>
        </label>
        <input
          id="franchise-name"
          type="text"
          value={values.name}
          onChange={handleChange('name')}
          disabled={saving}
          data-testid="franchise-name-input"
          className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-50 disabled:text-gray-400"
        />
      </div>

      <div>
        <label htmlFor="franchise-description" className="block text-sm font-medium text-gray-700 mb-1">
          Description
        </label>
        <textarea
          id="franchise-description"
          value={values.description}
          onChange={handleChange('description')}
          disabled={saving}
          rows={3}
          data-testid="franchise-description-input"
          className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-50 disabled:text-gray-400 resize-y"
        />
      </div>

      <div>
        <label htmlFor="franchise-display-order" className="block text-sm font-medium text-gray-700 mb-1">
          Display Order
        </label>
        <input
          id="franchise-display-order"
          type="number"
          min={0}
          value={values.display_order}
          onChange={handleChange('display_order')}
          disabled={saving}
          data-testid="franchise-display-order-input"
          className="w-32 px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-50 disabled:text-gray-400"
        />
      </div>

      <div>
        <label htmlFor="franchise-notes" className="block text-sm font-medium text-gray-700 mb-1">
          Notes
        </label>
        <textarea
          id="franchise-notes"
          value={values.notes}
          onChange={handleChange('notes')}
          disabled={saving}
          rows={3}
          data-testid="franchise-notes-input"
          className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-50 disabled:text-gray-400 resize-y"
        />
      </div>

      <SetupFormActions
        onSave={handleSave}
        onCancel={onCancel}
        onDeactivate={onDeactivate}
        onReactivate={onReactivate}
        saving={saving}
        isActive={isActive}
        saveTestId="franchise-save-button"
        cancelTestId="franchise-cancel-button"
        deactivateTestId="franchise-deactivate-button"
        reactivateTestId="franchise-reactivate-button"
      />
    </form>
  )
}
