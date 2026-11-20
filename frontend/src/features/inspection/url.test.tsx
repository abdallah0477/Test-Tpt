import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { UrlBar } from './UrlBar'
import { validateUrl } from './validateUrl'

afterEach(cleanup)

describe('validateUrl', () => {
  it.each(['http://127.0.0.1:8081/login', 'https://example.com', '  https://example.com/a?b=1  '])('accepts %s', (url) => {
    expect(validateUrl(url).ok).toBe(true)
  })

  it.each(['', 'example.com', 'ftp://example.com', 'javascript:alert(1)', 'file:///etc/passwd', 'http://'])(
    'rejects %j',
    (url) => {
      expect(validateUrl(url).ok).toBe(false)
    },
  )
})

describe('UrlBar', () => {
  it('shows a message and does not start for a malformed URL', () => {
    const onStart = vi.fn()
    render(<UrlBar busy={false} onStart={onStart} />)
    fireEvent.change(screen.getByLabelText('Page URL'), { target: { value: 'ftp://example.com' } })
    fireEvent.click(screen.getByRole('button', { name: 'Start inspection' }))
    expect(screen.getByRole('alert').textContent).toMatch(/only http and https/i)
    expect(onStart).not.toHaveBeenCalled()
  })

  it('starts with a valid URL', () => {
    const onStart = vi.fn()
    render(<UrlBar busy={false} onStart={onStart} />)
    fireEvent.change(screen.getByLabelText('Page URL'), { target: { value: 'https://example.com' } })
    fireEvent.click(screen.getByRole('button', { name: 'Start inspection' }))
    expect(onStart).toHaveBeenCalledWith('https://example.com')
  })
})
