// Loading skeleton shown while meeting data is pending.
export default function LoadingSkeleton({ className = "", as = "div" }) {
  const Tag = as;
  return <Tag className={`saas-skeleton ${className}`.trim()} aria-hidden="true" />;
}
