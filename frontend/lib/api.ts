import { Job, GenerationOptions } from "@/types"

export async function createJob(
  url: string,
  options: GenerationOptions
): Promise<{ jobId: string }> {
  const response = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, options }),
  })

  if (!response.ok) {
    throw new Error("Failed to create job")
  }

  return response.json()
}

export async function getJob(id: string): Promise<Job> {
  const response = await fetch(`/api/jobs/${id}`)
  if (!response.ok) {
    throw new Error("Failed to fetch job")
  }
  return response.json()
}
