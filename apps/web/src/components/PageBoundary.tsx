import { Component, ReactNode } from "react";

/** A rendering error on one page must never blank the whole console. */
export class PageBoundary extends Component<{ children: ReactNode; page: string }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidUpdate(prev: { page: string }) {
    if (prev.page !== this.props.page && this.state.error) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <section className="panel panel-pad refusal" style={{ borderRadius: 10 }}>
        <h2>This page could not be shown</h2>
        <p className="small" style={{ margin: "6px 0 12px" }}>
          Something in the data it received was not in the shape the page expected ({this.state.error.message}).
          Nothing in the platform was changed. Try again, or open another page.
        </p>
        <button className="btn" onClick={() => this.setState({ error: null })}>Try again</button>
      </section>
    );
  }
}
