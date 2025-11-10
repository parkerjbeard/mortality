import clsx from 'clsx'
import type { HTMLAttributes, ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Components } from 'react-markdown'

interface MarkdownContentProps {
  content: string
  className?: string
}

type CodeComponentProps = HTMLAttributes<HTMLElement> & {
  inline?: boolean
  className?: string
  children?: ReactNode
}

const CodeBlock = ({
  inline,
  className,
  children,
  ...props
}: CodeComponentProps) => {
  if (inline) {
    return (
      <code
        className={clsx(
          'rounded-md bg-black/30 px-1.5 py-0.5 font-mono text-[13px] text-slate-100',
          className,
        )}
        {...props}
      >
        {children}
      </code>
    )
  }
  return (
    <pre className="my-3 overflow-x-auto rounded-2xl bg-black/40 p-3 text-[13px] text-slate-100">
      <code
        className={clsx('font-mono text-[13px] text-slate-100', className)}
        {...props}
      >
        {children}
      </code>
    </pre>
  )
}

const markdownComponents: Components = {
  p: ({ node: _node, ...props }) => (
    <p
      {...props}
      className={clsx(
        'whitespace-pre-wrap text-sm leading-relaxed text-slate-100',
        props.className,
      )}
    />
  ),
  ul: ({ node: _node, ...props }) => (
    <ul
      {...props}
      className={clsx(
        'my-2 list-disc space-y-1 pl-5 text-slate-100',
        props.className,
      )}
    />
  ),
  ol: ({ node: _node, ...props }) => (
    <ol
      {...props}
      className={clsx(
        'my-2 list-decimal space-y-1 pl-5 text-slate-100',
        props.className,
      )}
    />
  ),
  li: ({ node: _node, ...props }) => (
    <li
      {...props}
      className={clsx(
        'text-sm leading-relaxed text-slate-100',
        props.className,
      )}
    />
  ),
  a: ({ node: _node, ...props }) => (
    <a
      {...props}
      className={clsx(
        'font-semibold text-accent underline decoration-dotted underline-offset-4 transition hover:text-accent/80',
        props.className,
      )}
      target="_blank"
      rel="noreferrer"
    />
  ),
  blockquote: ({ node: _node, ...props }) => (
    <blockquote
      {...props}
      className={clsx(
        'my-3 border-l-2 border-accent/50 pl-4 text-sm italic leading-relaxed text-slate-200',
        props.className,
      )}
    />
  ),
  code: CodeBlock,
  hr: ({ node: _node, ...props }) => (
    <hr {...props} className={clsx('my-4 border-white/10', props.className)} />
  ),
}

export const MarkdownContent = ({
  content,
  className,
}: MarkdownContentProps) => {
  if (!content.trim()) {
    return null
  }

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={markdownComponents}
      className={clsx(
        'markdown-body space-y-2 text-sm text-slate-100',
        className,
      )}
    >
      {content}
    </ReactMarkdown>
  )
}
