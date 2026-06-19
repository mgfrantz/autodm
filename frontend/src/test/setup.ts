/**
 * Test bootstrap — loaded before every test file via vitest `setupFiles`.
 *
 * Extends vitest's `expect` with the DOM matchers from
 * @testing-library/jest-dom (toBeInTheDocument, toBeDisabled, toHaveTextContent, …).
 */
import '@testing-library/jest-dom/vitest'
