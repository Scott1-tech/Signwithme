import { CompanyDetails } from "@/components/settings/company-details";
import { FieldMapEditor } from "@/components/settings/field-map-editor";
import { ProbeTool } from "@/components/settings/probe-tool";
import { SignatureSettings } from "@/components/settings/signature-settings";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export const metadata = { title: "Settings · Contract Review Desk" };

export default function SettingsPage() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Point the field map at your contract&apos;s wording, then get the
          signature landing in the right place. Configure once per contract
          type.
        </p>
      </div>

      <Tabs defaultValue="fields">
        <TabsList>
          <TabsTrigger value="fields">Field mapping</TabsTrigger>
          <TabsTrigger value="signature">Signature</TabsTrigger>
          <TabsTrigger value="company">Company details</TabsTrigger>
        </TabsList>

        <TabsContent value="fields" className="space-y-6">
          <FieldMapEditor />
          <Separator />
          <ProbeTool />
        </TabsContent>

        <TabsContent value="signature">
          <SignatureSettings />
        </TabsContent>

        <TabsContent value="company">
          <CompanyDetails />
        </TabsContent>
      </Tabs>
    </div>
  );
}
